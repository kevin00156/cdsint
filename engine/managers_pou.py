# -*- coding: utf-8 -*-
"""The managers for textual objects: POUs and their members, and properties.

A property is a POU member whose get/set accessors are objects of their
own in the IDE and one file on disk.

Moved out of codesys_managers.py unchanged.
"""
from __future__ import print_function

import os
from engine.codesys_utils import (
    safe_str,
    log_error,
    log_warning,
    format_st_content,
    format_property_content,
    parse_property_content,
    read_ide_attrs,
    write_ide_attrs,
    render_sync_pragmas,
    build_state_hash,
    parse_sync_pragmas,
    attrs_from_pragmas,
    needs_kind_pragma,
    read_sync_text,
)
from engine.codesys_constants import IMPLEMENTATION_TYPES, kind_of
from engine.managers_base import ObjectManager
from engine.object_content import (
    export_object_content,
    parse_accessor_content,
    update_object_code,
)


class POUManager(ObjectManager):
    """Handle standard textual objects (POUs, GVLs, DUTs)"""

    # Kinds whose IDE object is a MEMBER of a parent POU/interface, mapped to
    # the ScriptEngine creator the container must expose. Keyed by KIND, not by
    # GUID: 'itf_method' is a distinct GUID from 'method' (a method on an
    # interface), and comparing GUIDs directly left it with no creator at all.
    MEMBER_CREATORS = {
        "method": "create_method",
        "itf_method": "create_method",
        "property": "create_property",
        "action": "create_action",
    }

    # Top-level kinds with a dedicated creator; anything else uses create_pou.
    TOPLEVEL_CREATORS = {
        "gvl": "create_gvl",
        "dut": "create_dut",
        "itf": "create_interface",
    }

    def export(self, obj, effective_type, rel_path, context):
        # Determine target directory and file path
        file_path = os.path.join(context['export_dir'], rel_path.replace("/", os.sep))

        # --- CACHE SKIP OPTIMIZATION ---
        skip = self._try_cache_skip(obj, rel_path, file_path, context, is_xml=False)
        if skip:
            return skip
        # -------------------------------

        declaration, implementation = export_object_content(obj, self.project)
        # Check if this object type can have implementation even if empty
        obj_type_guid = safe_str(obj.type)
        can_have_impl = obj_type_guid in IMPLEMENTATION_TYPES
        clean_content = format_st_content(declaration, implementation, can_have_impl)

        if not clean_content.strip():
            return False

        # Read IDE attributes and render sync pragmas. Kinds the ST text
        # alone cannot express (persistent GVL, action, ...) also get a kind
        # pragma so import can recreate the right object kind. The kind is
        # identity metadata: it goes in the file but NOT in the state hash.
        attrs = read_ide_attrs(obj, obj_type_guid)
        pragmas = dict(attrs)
        obj_kind = kind_of(effective_type)
        if obj_kind and needs_kind_pragma(obj_kind, clean_content):
            pragmas["kind"] = obj_kind
        content = render_sync_pragmas(pragmas, clean_content)

        return self._write_text(obj, rel_path, file_path, content,
                                build_state_hash(clean_content, attrs), context)

    def update(self, obj, file_path):
        from engine.codesys_utils import parse_st_file
        declaration, implementation, pragmas = parse_st_file(file_path)
        if declaration is None and implementation is None:
            return False

        # We assume the engine already decided we need to update based on content hash
        updated = update_object_code(obj, declaration, implementation)
        write_ide_attrs(obj, attrs_from_pragmas(pragmas))
        return updated

    def create(self, container, name, file_path, type_guid):
        from engine.codesys_utils import parse_st_file
        declaration, implementation, pragmas = parse_st_file(file_path)

        obj = None
        try:
            special_kind = kind_of(type_guid) if type_guid else None
            if special_kind in ("persistent_gvl", "task_local_gvl", "param_list"):
                obj = self._create_special_gvl(container, name, type_guid, special_kind)
                if obj is None:
                    return None
            elif special_kind in self.MEMBER_CREATORS:
                obj = self._create_member(container, name, special_kind)
                if obj is None:
                    return None
            elif (special_kind in self.TOPLEVEL_CREATORS
                  and hasattr(container, self.TOPLEVEL_CREATORS[special_kind])):
                obj = getattr(container, self.TOPLEVEL_CREATORS[special_kind])(name)
            elif hasattr(container, "create_pou"):
                # Always create as Program first — update_object_code will replace
                # the declaration with the correct FUNCTION / FUNCTION_BLOCK header.
                #
                # PouType is a CODESYS global the IDE injects into the running
                # script's namespace, and the entry body hands it here rather
                # than this module going to look for it. It is not an import,
                # and it is not a global of this module either -- reading a
                # bare `PouType` here never resolved.
                if self.pou_type is not None:
                    obj = container.create_pou(name, self.pou_type.Program)
                else:
                    log_error("No PouType was handed to this manager. Falling "
                              "back to create_child.")
                    obj = container.create_child(name, type_guid) if hasattr(container, "create_child") else None
            elif hasattr(container, "create_child"):
                obj = container.create_child(name, type_guid)
                
            if obj:
                update_object_code(obj, declaration, implementation)
                write_ide_attrs(obj, attrs_from_pragmas(pragmas))
                return obj
        except Exception as e:
            log_error("Failed to create " + name + ": " + safe_str(e))
        return None

    def _create_member(self, container, name, kind):
        """Create a method/action/property on its parent POU or interface.

        Fails loud instead of falling through to create_pou(). A container that
        exposes no creator for the kind means the caller resolved the wrong
        parent - typically a FOLDER that shares its name with the POU inside it
        ("Function Blocks/MC_BasicControl/MC_BasicControl"). Creating a
        standalone PROGRAM there produced a stray object that the next compare
        then deleted as an orphan, so every import created and destroyed the
        same objects in a loop.
        """
        creator = self.MEMBER_CREATORS[kind]
        if not hasattr(container, creator):
            log_error("Cannot create %s '%s': its container %s exposes no %s(). "
                      "The parent POU/interface was not resolved - refusing to "
                      "create a stray standalone object in its place."
                      % (kind, name, safe_str(container), creator))
            return None
        obj = getattr(container, creator)(name)
        if obj is None:
            log_error("%s('%s') returned nothing on %s (kind=%s)."
                      % (creator, name, safe_str(container), kind))
        return obj

    def _create_special_gvl(self, container, name, type_guid, kind):
        """Create GVL variants that ST syntax alone cannot express
        (persistent GVL, task-local GVL, parameter list).

        Tries a kind-specific creator if the container exposes one, then the
        generic typed child API. Fails loud on purpose: before the kind
        pragma existed these files fell through to the create_pou fallback
        and were silently created as PROGRAM POUs.
        """
        attempted = []

        creator_candidates = {
            "persistent_gvl": ["create_persistent_gvl"],
            "task_local_gvl": ["create_task_local_gvl"],
            "param_list": ["create_parameter_list"],
        }
        for creator in creator_candidates.get(kind, []):
            if hasattr(container, creator):
                attempted.append(creator)
                try:
                    obj = getattr(container, creator)(name)
                    if obj:
                        return obj
                except Exception as e:
                    log_warning("%s('%s') failed: %s" % (creator, name, safe_str(e)))

        if hasattr(container, "create_child"):
            attempted.append("create_child")
            try:
                obj = container.create_child(name, type_guid)
                if obj:
                    return obj
            except Exception as e:
                log_warning("create_child('%s', %s) failed: %s" % (name, type_guid, safe_str(e)))

        log_error("Cannot create %s '%s': this CODESYS version exposes no "
                  "scriptable creation API for that kind (tried: %s). Create "
                  "the object manually in the IDE, then re-import to fill in "
                  "its content." % (kind, name, ", ".join(attempted) or "none"))
        return None


class PropertyManager(POUManager):
    """Handle properties specifically (combining declaration, Get, and Set)"""
    def export(self, obj, effective_type, rel_path, context):
        obj_guid = safe_str(obj.guid)

        if obj_guid not in context['property_accessors']:
            prop_data = {'get': None, 'set': None, 'parent_obj': obj}
        else:
            prop_data = context['property_accessors'][obj_guid]

        # Determine target directory and file path
        file_path = os.path.join(context['export_dir'], rel_path.replace("/", os.sep))

        # --- CACHE SKIP OPTIMIZATION ---
        skip = self._try_cache_skip(obj, rel_path, file_path, context, is_xml=False)
        if skip:
            return skip
        # -------------------------------

        # Export Declaration
        declaration, _ = export_object_content(obj, self.project)
        
        # Get GET accessor
        get_impl = None
        if prop_data['get']:
            get_decl, get_impl_raw = export_object_content(prop_data['get'], self.project)
            get_impl = format_st_content(get_decl, get_impl_raw)
            
        # Get SET accessor
        set_impl = None
        if prop_data['set']:
            set_decl, set_impl_raw = export_object_content(prop_data['set'], self.project)
            set_impl = format_st_content(set_decl, set_impl_raw)
            
        # Combine into Property Format
        combined_content = format_property_content(declaration, get_impl, set_impl)

        # Read IDE attributes and render sync pragmas
        attrs = read_ide_attrs(obj)
        content = render_sync_pragmas(attrs, combined_content)
        content_hash = build_state_hash(combined_content, attrs)

        return self._write_text(obj, rel_path, file_path, content,
                                content_hash, context)

    def update(self, obj, file_path):
        try:
            raw_content = read_sync_text(file_path)
        except: return False

        pragmas, clean_content = parse_sync_pragmas(
            raw_content.replace('\r\n', '\n').replace('\r', '\n'))

        declaration, get_impl_combined, set_impl_combined = parse_property_content(clean_content)
        updated = False
        
        if declaration and update_object_code(obj, declaration, None):
            updated = True
            
        # Update GET accessor
        if get_impl_combined:
            for child in obj.get_children():
                if child.get_name().lower() == "get":
                    g_decl, g_code = parse_accessor_content(get_impl_combined)
                    if update_object_code(child, g_decl, g_code):
                        updated = True
                    break
                    
        # Update SET accessor
        if set_impl_combined:
            for child in obj.get_children():
                if child.get_name().lower() == "set":
                    s_decl, s_code = parse_accessor_content(set_impl_combined)
                    if update_object_code(child, s_decl, s_code):
                        updated = True
                    break

        # Unconditional so a pragma removed on disk clears the IDE flag
        # (same semantics as POUManager.update).
        write_ide_attrs(obj, attrs_from_pragmas(pragmas))

        return updated

    def create(self, container, name, file_path, type_guid):
        try:
            raw_content = read_sync_text(file_path)
        except: return None

        pragmas, clean_content = parse_sync_pragmas(
            raw_content.replace('\r\n', '\n').replace('\r', '\n'))

        declaration, get_impl_combined, set_impl_combined = parse_property_content(clean_content)

        obj = None
        try:
            if hasattr(container, "create_property"):
                obj = container.create_property(name)
            elif hasattr(container, "create_child"):
                obj = container.create_child(name, type_guid)
                
            if obj:
                if declaration:
                    update_object_code(obj, declaration, None)
                
                if get_impl_combined and hasattr(obj, "create_get_accessor"):
                    get_obj = obj.create_get_accessor()
                    g_decl, g_code = parse_accessor_content(get_impl_combined)
                    update_object_code(get_obj, g_decl, g_code)
                    
                if set_impl_combined and hasattr(obj, "create_set_accessor"):
                    set_obj = obj.create_set_accessor()
                    s_decl, s_code = parse_accessor_content(set_impl_combined)
                    update_object_code(set_obj, s_decl, s_code)

                attrs = attrs_from_pragmas(pragmas)
                if attrs:
                    write_ide_attrs(obj, attrs)

                return obj
        except Exception as e:
            log_error("Failed to create property " + name + ": " + safe_str(e))
        return None
