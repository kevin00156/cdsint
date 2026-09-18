# -*- coding: utf-8 -*-
"""Putting one file's content into the IDE: update the object, or create it.

A POU's actions, methods and properties are children the IDE deletes with
it, so an update that recreates the POU saves them first and puts them
back. Native XML kinds go in as a batch.

Moved out of codesys_compare_engine.py unchanged.
"""
from __future__ import print_function

import os
import tempfile
from engine.codesys_constants import (
    TYPE_GUIDS,
    XML_TYPES,
    kind_of,
    sync_direction_of,
    kind_allows_import,
)
from engine.ide_tree import (
    find_object_by_path,
    ensure_folder_path,
    find_object_by_name,
    find_child_transparent,
)
from engine.st_text import (
    merge_native_xmls,
    parse_st_file,
    determine_object_type,
)
from engine.strings import safe_str
from engine.sync_log import log_info, log_error, log_warning
from engine.pou_children import restore_pou_children
from engine.classify import manager_for
from engine import unhandled
from engine.ide_read import child_named


def _is_xml_backed(rel_path, type_guid):
    """Is this object stored as native XML rather than as ST text?

    Export is told by classify_object. Import has to work it out, and the disk
    file is the truth (PRINCIPLES 5), so the suffix answers first. The type is
    the second half of the answer for a file that has not been written yet --
    a create_new_object() whose path has no extension to read.
    """
    return rel_path.endswith(".xml") or type_guid in XML_TYPES


def update_existing_object(obj, rel_path, file_path, import_managers):
    """Update an existing IDE object from a disk file.

    An import always forces the content through; the manager's update() is
    the one that checks whether the IDE side would actually change.
    """
    type_guid = safe_str(obj.type)
    manager = manager_for(import_managers, type_guid, _is_xml_backed(rel_path, type_guid))
    return manager.update(obj, file_path)


def _is_pou_or_itf(obj):
    """True when obj is a POU or an interface — the only kinds that can hold a
    method/action/property.

    A name match alone never identifies a member's parent: the export lays a
    POU's members out under a folder named after the POU
    ("Function Blocks/MC_BasicControl/MC_BasicControl.Main.st"), so the folder
    and the POU inside it share a name.
    """
    if obj is None:
        return False
    try:
        return kind_of(safe_str(obj.type)) in ("pou", "itf")
    except Exception:
        return False


def find_parent_pou(container, parent_name):
    """Find the POU/interface named parent_name in or below container.

    find_child_transparent() matches on name only and will happily return a
    same-named FOLDER; members must land on the POU itself, so a folder hit is
    treated as one more level to look through.
    """
    found = find_child_transparent(container, parent_name)
    if _is_pou_or_itf(found):
        return found
    if found is not None:
        inner = find_child_transparent(found, parent_name)
        if _is_pou_or_itf(inner):
            return inner
    return None


def create_new_object(rel_path, file_path, import_managers, name_map,
                      folder_cache, project):
    """Create a new IDE object from a disk file."""
    path_parts = rel_path.split("/")
    
    # Ensure parent folder structure exists
    if len(path_parts) > 1:
        folder_path = "/".join(path_parts[:-1])
        if folder_path in folder_cache:
            container = folder_cache[folder_path]
        else:
            container = ensure_folder_path(folder_path, project)
            folder_cache[folder_path] = container
    else:
        container = project
        
    if not container:
        log_error("Could not find or create container for " + rel_path)
        return None
    
    base_name = os.path.splitext(path_parts[-1])[0]
    
    if rel_path.endswith(".xml"):
        # XML files are handled by batch_import_native_xmls_with_children
        return None
    
    decl, impl, pragmas = parse_st_file(file_path)
    content_check = decl if decl else impl
    if not content_check:
        return None

    # The kind pragma wins over keyword sniffing: it carries the object
    # kinds ST syntax alone cannot express (persistent GVL vs plain GVL,
    # action bodies, ...). The kind name maps to the CURRENT profile's
    # primary GUID, so files stay portable across CODESYS versions.
    type_guid = determine_object_type(content_check)
    kind_pragma = pragmas.get("kind")
    if kind_pragma:
        # kind_of() also resolves retired kind names, so a pragma written by an
        # older version still maps onto the current profile's primary GUID.
        pragma_guid = TYPE_GUIDS.get(kind_of(kind_pragma))
        if not pragma_guid:
            log_error("Unknown kind '%s' in pragma of %s - add it to "
                      "guid_aliases in profiles/default.json. Skipping creation."
                      % (kind_pragma, rel_path))
            return None
        type_guid = pragma_guid

    # Handle nested objects (Action, Method, Property)
    # A dotted base_name like "ST_PROGRAMM.ST_ACTION" means it's a child object.
    # We check both: (a) when type_guid indicates a child type, and
    #                 (b) when type_guid is None/unknown but filename has a dot.
    name = base_name
    nested_types = [TYPE_GUIDS.get("action"), TYPE_GUIDS.get("method"),
                    TYPE_GUIDS.get("property"), TYPE_GUIDS.get("property_accessor"),
                    TYPE_GUIDS.get("itf_method")]
    is_nested = "." in base_name and (
        type_guid in nested_types or       # Known child type (method, property, etc.)
        not type_guid or                   # Unknown type (e.g. action with no keyword)
        type_guid == TYPE_GUIDS.get("pou") # Misdetected as POU
    )
    if is_nested:
        parts = base_name.rsplit(".", 1)
        parent_name = parts[0]
        child_name = parts[1]
        log_info("Looking for parent POU: " + parent_name + " for child: " + child_name)

        # Resolve the parent POU using several strategies, in order:
        #   1. Objects created earlier in this same import session (name_map).
        #   2. The already-resolved container may BE the parent FB — but only
        #      when it is actually a POU/interface. The container is usually the
        #      grouping FOLDER, which shares the FB's name; accepting it here
        #      created every method as a stray standalone POU beside the real FB.
        #   3. The parent POU normally lives directly inside the container
        #      (grouping-folder layout "<FB>/<FB>.Method.st" and stripped layout
        #      "<FB>.Method.st" both put the FB as a direct child of `container`).
        #   4. Legacy path lookup for an extra nested-folder layout.
        pou_parent = find_object_by_name(parent_name, name_map)
        if not _is_pou_or_itf(pou_parent):
            pou_parent = None

        if not pou_parent and _is_pou_or_itf(container):
            try:
                if container.get_name() == parent_name:
                    pou_parent = container
            except:
                pass
        if not pou_parent:
            pou_parent = find_parent_pou(container, parent_name)

        if not pou_parent:
            parent_path = "/".join(path_parts[:-1])
            parent_path_with_name = parent_path + "/" + parent_name
            log_info("Parent '" + parent_name + "' not in container, trying path: " + parent_path_with_name)
            pou_parent = find_object_by_path(parent_path_with_name, project)
            if not _is_pou_or_itf(pou_parent):
                pou_parent = None

        if pou_parent:
            log_info("Found parent POU: " + safe_str(pou_parent))
            name = child_name
            container = pou_parent
            # If type_guid wasn't determined, infer from child name patterns
            if not type_guid or type_guid == TYPE_GUIDS.get("pou"):
                upper_child = child_name.upper()
                if upper_child in ("GET", "SET"):
                    type_guid = TYPE_GUIDS.get("property_accessor")
                else:
                    # Default to action for unknown nested children
                    type_guid = TYPE_GUIDS.get("action")
        else:
            # Never fall back to creating a POU with a dotted name — CODESYS
            # rejects object names containing '.'. Skip and report instead.
            log_error("Could not find parent POU '" + parent_name + "' for child '" +
                      child_name + "' (" + rel_path + "). Skipping to avoid invalid dotted-name object.")
            return None

    # Direction re-check now that the kind is known from the file content
    # (new .st items reach perform_import_items without a type_guid).
    created_kind = kind_of(type_guid or "")
    if created_kind and not kind_allows_import(created_kind):
        msg = ("Skipping creation of '%s' (%s): sync_direction=%s"
               % (rel_path, created_kind, sync_direction_of(created_kind)))
        print("  [!] " + msg)
        log_warning(msg)
        return None

    manager = manager_for(import_managers, type_guid,
                          _is_xml_backed(rel_path, type_guid))
    res = manager.create(container, name, file_path, type_guid)
    
    if res:
        obj_name = res.get_name()
        if obj_name not in name_map:
            name_map[obj_name] = []
        name_map[obj_name].append(res)
        log_info("Created " + rel_path)
    else:
        log_error("Failed to create " + rel_path)
    
    return res


def batch_import_native_xmls_with_children(native_batches, import_managers, project, pou_children_info=None):
    """
    Process batched native XML imports to reduce dialogs.
    Restores POU children after XML import to prevent deletion.
    
    Args:
        native_batches: dict of {container: [(rel_path, abs_path, name, type_guid, is_new), ...]}
        import_managers: dict of managers
        project: CODESYS project
        pou_children_info: dict of {pou_name_lower: saved_children} to restore after import
    
    Returns:
        (updated_count, created_count, failed_count)
    """
    if pou_children_info is None:
        pou_children_info = {}
    
    updated = 0
    created = 0
    failed = 0
    
    for container, items in native_batches.items():
        print("  Batch importing " + str(len(items)) + " native objects into " + safe_str(container))
        temp_xml = os.path.join(tempfile.gettempdir(), "cds_sync_batch.xml")
        file_paths = [item[1] for item in items]
        
        if merge_native_xmls(file_paths, temp_xml):
            try:
                if hasattr(container, "import_native"):
                    container.import_native(temp_xml)
                else:
                    project.import_native(temp_xml)
                
                # Restore POU children after XML import
                # Find POUs by name in the container
                for rel_path, file_path, name, type_guid, is_new in items:
                    pou_name_lower = name.lower()
                    if pou_name_lower in pou_children_info:
                        children = pou_children_info[pou_name_lower]
                        pou_obj = child_named(container, name)
                        if pou_obj:
                            try:
                                restore_pou_children(pou_obj, children, import_managers, project)
                            except Exception as e:
                                log_warning("Could not restore children for POU " + name + ": " + safe_str(e))
                
                for rel_path, file_path, name, type_guid, is_new in items:
                    res = child_named(container, name)
                    if res:
                        if is_new:
                            created += 1
                        else:
                            updated += 1
                            print("  Updated (native batch): " + rel_path)
                    else:
                        log_error("Batch import could not find " + name + " after import.")
                        unhandled.note(name, "not found after batch import")
                        failed += 1
                        
            except Exception as e:
                log_error("Batch import failed for " + safe_str(container) + ": " + safe_str(e))
                for queued in items:
                    unhandled.note(queued[2], e)
                failed += len(items)
        else:
            log_error("Failed to merge XML for " + safe_str(container))
            for queued in items:
                unhandled.note(queued[2], "XML for its container could not be merged")
            failed += len(items)
        
        if os.path.exists(temp_xml):
            try:
                os.remove(temp_xml)
            except:
                pass
    
    return updated, created, failed
