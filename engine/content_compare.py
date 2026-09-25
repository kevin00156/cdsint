# -*- coding: utf-8 -*-
"""Is what the IDE holds the same as what the file says?

get_ide_content() renders an object the way export would; contents_are_equal()
compares that against the disk with the pragmas stripped and, for native
XML, with the lines the IDE rewrites on every export ignored.

Moved out of codesys_compare_engine.py unchanged.
"""
from __future__ import print_function

import os
from cds.core import library_list
from engine import library_refs
from engine.codesys_constants import TYPE_GUIDS
from engine.ide_attrs import read_ide_attrs
from engine.st_text import (
    format_st_content,
    format_property_content,
    parse_sync_pragmas,
    normalize_sync_attrs,
    read_sync_text,
)
from engine.strings import safe_str, calculate_hash
from engine.sync_log import log_info, log_warning
from engine.managers_native import NativeManager
from engine.object_content import export_object_content
from engine.object_kind import native_xml_of
from engine import unhandled


# The managers are stateless; one shared instance spares the engine from
# constructing a new one inside per-object comparison loops.
_NATIVE_MGR = NativeManager()


def get_ide_content(obj, is_xml, property_accessors, project, can_have_impl=False):
    """Extract content and attributes from IDE object for comparison.

    Returns:
        (ide_content, ide_attrs) where ide_attrs is a dict of non-default
        build attributes, or empty dict for XML objects or on error.
    """
    # Read the type once and pass it down; both branches below needed it and
    # read_ide_attrs re-read it a third time.
    obj_type = safe_str(obj.type)
    if obj_type == TYPE_GUIDS["library_manager"]:
        # Its text is built from the script API, not from a declaration
        # (SPEC 6.9), and it has no build attributes.
        return library_refs.render_ide(obj), {}
    if is_xml:
        return _native_content(obj, obj_type, project), {}
    ide_attrs = read_ide_attrs(obj, obj_type)

    # ST content
    obj_guid = safe_str(obj.guid)

    if obj_type == TYPE_GUIDS["property"] and obj_guid in property_accessors:
        prop_data = property_accessors[obj_guid]
        declaration, _ = export_object_content(obj, project)

        get_impl = None
        if prop_data['get']:
            get_decl, get_impl_raw = export_object_content(prop_data['get'], project)
            get_impl = format_st_content(get_decl, get_impl_raw, False)

        set_impl = None
        if prop_data['set']:
            set_decl, set_impl_raw = export_object_content(prop_data['set'], project)
            set_impl = format_st_content(set_decl, set_impl_raw, False)

        return format_property_content(declaration, get_impl, set_impl), ide_attrs

    declaration, implementation = export_object_content(obj, project)
    return format_st_content(declaration, implementation, can_have_impl), ide_attrs


def _native_content(obj, obj_type, project):
    """An XML-backed object's native XML, or "" when it could not be read."""
    try:
        # ConfigManager objects require recursive=True to include all children
        monolithic_types = [
            TYPE_GUIDS["task_config"], TYPE_GUIDS["alarm_config"],
            TYPE_GUIDS["visu_manager"], TYPE_GUIDS["softmotion_pool"]
        ]
        recursive = obj_type in monolithic_types

        # Special logic for devices: only recursive if not a project container
        if obj_type == TYPE_GUIDS["device"]:
            from engine.ide_tree import is_container_device
            recursive = not is_container_device(obj)

        content = native_xml_of(project, obj, recursive)
        if content is not None:
            return content
    except Exception as exc:
        # "" reads downstream as "the IDE side is empty", which compares
        # as different and re-exports the object -- wrong, but harmless.
        # An object nobody could read is not harmless, so say whose (D13).
        unhandled.note(obj, exc)
        log_warning("Could not read the native XML of %s: %s"
                    % (unhandled.name_of(obj), safe_str(exc)))
    return ""


def contents_are_equal(ide_content, disk_content, is_xml, rel_path="unknown",
                       ide_attrs=None, disk_attrs=None):
    """Compare two content strings, with XML-specific filtering.

    For ST files, sync pragmas are stripped from the disk content before the
    code comparison, and the pragma attributes are compared separately when
    both attr dicts are provided. Returns True only if code AND attributes
    match.
    """
    if rel_path.endswith(library_list.SUFFIX):
        # Compared as entries, so a comment or spacing is not a difference.
        return library_list.same(ide_content or "", disk_content or "")
    if not ide_content or not disk_content:
        return ide_content == disk_content

    if not is_xml:
        # For ST files: strip pragmas from disk content for code comparison
        _, clean_disk_st = parse_sync_pragmas(disk_content)
        ide_hash = calculate_hash(ide_content)
        disk_hash = calculate_hash(clean_disk_st)
        if ide_hash != disk_hash:
            log_info("Content mismatch for %s: IDE hash=%s, Disk hash=%s" % (rel_path, ide_hash, disk_hash))
            return False

        # Code matches - now compare attributes
        if ide_attrs is not None and disk_attrs is not None:
            if normalize_sync_attrs(ide_attrs) != normalize_sync_attrs(disk_attrs):
                from engine.codesys_constants import ATTR_ORDER
                attr_diff = []
                for k in ATTR_ORDER:
                    if ide_attrs.get(k) != disk_attrs.get(k):
                        attr_diff.append("%s: IDE=%s Disk=%s" % (k, ide_attrs.get(k), disk_attrs.get(k)))
                log_info("Attribute mismatch for %s: %s" % (rel_path, ", ".join(attr_diff)))
                return False

        return True
    
    # XML Comparison - use NativeManager's filtering logic. Both sides are
    # already in memory, so hash them directly; this used to write each one to
    # a temp file and read it back purely because _hash_file only took a path.
    # The two fallback names below are the old temp filenames, kept so that an
    # object whose content is entirely filtered away still compares as
    # different exactly like before (see _hash_content).
    try:
        ide_hash = _NATIVE_MGR._hash_content(ide_content, "cds_comp_ide.xml")
        disk_hash = _NATIVE_MGR._hash_content(disk_content, "cds_comp_disk.xml")

        are_equal = ide_hash == disk_hash
        if not are_equal:
            log_info("Content match: IDE hash=%s, Disk hash=%s" % (ide_hash, disk_hash))
            log_info("Content mismatch for %s (XML)" % rel_path)
        return are_equal
    except Exception as e:
        log_warning("Error comparing XML contents for %s: %s" % (rel_path, str(e)))
        return False


def read_file(file_path):
    """Disk content for the comparison, or "" when there is none to be had."""
    if not os.path.exists(file_path):
        return ""
    try:
        return read_sync_text(file_path)
    except:
        return ""
