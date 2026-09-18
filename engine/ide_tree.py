# -*- coding: utf-8 -*-
"""Finding and making places in the IDE object tree.

A path on disk becomes a chain of names; these walk the live tree to the
object that chain names, seeing through the containers export does not
write as folders, and create the folders an import needs.

Moved out of codesys_utils.py unchanged.
"""
from __future__ import print_function

import os
from engine.unhandled import name_of
from engine.codesys_constants import TYPE_GUIDS
from engine.strings import safe_str
from engine.sync_log import log_warning


def is_container_device(obj):
    """
    Check if a device is a 'container' (like a PLC root) that contains logic/applications.
    Such devices should NOT be monolithic XMLs because they are too large and
    their children (Applications, etc.) are already handled separately.
    """
    try:
        obj_type = safe_str(obj.type)
        if obj_type != TYPE_GUIDS["device"]:
            return False
            
        # Check if it has an Application or Plc Logic child
        # We only check direct children to avoid heavy recursion
        children = obj.get_children(recursive=False)
        for child in children:
            child_type = safe_str(child.type)
            if child_type in [TYPE_GUIDS["application"], TYPE_GUIDS["plc_logic"]]:
                return True
        return False
    except:
        return False


def find_child_transparent(parent_obj, name):
    """
    Find a child object by name, transparently looking through 'Plc Logic' nodes.
    
    The export skips 'Plc Logic' in paths (e.g. PLC/ST_Application instead of
    PLC/Plc Logic/ST_Application). This helper first checks direct children, then
    looks through any plc_logic children for the target name.
    
    Returns the found object or None.
    """
    if not parent_obj or not name:
        return None
    
    name_lower = name.lower()
    
    try:
        children = parent_obj.get_children()
    except:
        return None
    
    # First pass: direct child match
    for child in children:
        try:
            if child.get_name().lower() == name_lower:
                return child
        except:
            continue
    
    # Not found directly, so look through 'plc_logic' transparently: the
    # export skips that node in paths, so the disk never names it.
    # (the export skips this level in the path)
    for child in children:
        try:
            c_type = safe_str(child.type)
            if c_type == TYPE_GUIDS.get("plc_logic"):
                for grandchild in child.get_children():
                    try:
                        if grandchild.get_name().lower() == name_lower:
                            return grandchild
                    except:
                        continue
        except:
            continue
    
    return None


def strip_src_prefix(path_str):
    """Drop the retired "src/" the earliest exports wrote in front of paths.

    One reader for it, because two spellings of the same migration drift: a
    path that keeps its prefix on one side and loses it on the other resolves
    to two different places in the tree.
    """
    normalized = path_str.replace("\\", "/")
    if normalized.startswith("src/"):
        return normalized[4:]
    return normalized


def _create_folder(container, name):
    """Make one folder under container and hand it back.

    Two calls do this depending on the CODESYS version, and either of them
    may create the folder and still return something falsy -- so the folder
    is looked up again rather than trusted to come back. That re-scan is a
    documented quirk, not a retry: it runs once, and if the folder is still
    not there this raises rather than returning a None the caller would carry
    on with (SPEC D13, PRINCIPLES 6).
    """
    made = None
    try:
        if hasattr(container, "create_folder"):
            made = container.create_folder(name)
        elif hasattr(container, "create_child"):
            made = container.create_child(name, TYPE_GUIDS["folder"])
        else:
            raise RuntimeError(
                "cannot create '%s' under %s: it exposes neither "
                "create_folder() nor create_child()"
                % (name, name_of(container)))
    except Exception as exc:
        # The folder may exist anyway; the exception can come from the part
        # of the call that happens after it was made.
        made = None
        log_warning("create folder '%s' raised: %s" % (name, safe_str(exc)))

    if made:
        return made
    found = find_child_transparent(container, name)
    if found:
        return found
    raise RuntimeError("could not create the folder '%s' under %s"
                       % (name, name_of(container)))


def ensure_folder_path(path_str, project):
    """Walk (and create) the folder path, and hand back the object it ends at.

    path_str is a relative path like "PLC/Application/MainFolder". The export
    skips 'Plc Logic' nodes, so the lookup looks through those transparently.

    Raises when a component cannot be found or made, rather than answering
    None. The caller is inside the per-object step of an import, which records
    the object by name and carries on with the rest (SPEC D13); a None would
    travel one frame further and become an object created in the wrong place.
    """
    if not path_str or path_str == "." or path_str == "src":
        return project

    current = project
    for part in strip_src_prefix(path_str).split("/"):
        if not part:
            continue
        current = find_child_transparent(current, part) or _create_folder(current, part)
    return current


def find_object_by_name(name, name_map):
    """
    Find a CODESYS object by name using cache.
    Returns first match or None.

    Several objects can share a name, and this answers with the first of
    them. Nothing breaks that tie, because the one caller has nothing to
    break it with: it looks a parent POU's name up in a map it built itself,
    and takes whatever comes back or nothing.
    """
    found = name_map.get(name)
    if not found:
        return None
    return found[0]


def find_object_by_path(rel_path, project):
    """
    Find a CODESYS object using its hierarchical path.
    Example rel_path: "PLC/ST_Application/02_Object_GVL/_02_TaskLocalGVL.xml"
    
    Note: The export skips 'Plc Logic' nodes in paths, so this function
    transparently looks through plc_logic children when a direct match
    isn't found.
    """
    if not rel_path: return None
    
    path_str = strip_src_prefix(rel_path)
    
    # Strip extension for lookup
    root, ext = os.path.splitext(path_str)
    parts = root.split("/")
    
    # Handle New Format: Name.Type.xml
    if ext.lower() == ".xml" and parts:
        last_part = parts[-1]
        if "." in last_part:
            name_part, doc_type = last_part.rsplit(".", 1)
            # Verify if doc_type is a known CODESYS type name. Retired kind
            # names count too - old exports on disk still carry them.
            from engine.codesys_constants import KNOWN_TYPE_SUFFIXES
            if doc_type in KNOWN_TYPE_SUFFIXES:
                parts[-1] = name_part

    current_obj = project
    for part in parts:
        if not part: continue
        found = find_child_transparent(current_obj, part)
        
        if found:
            current_obj = found
        else:
            return None
            
    return current_obj
