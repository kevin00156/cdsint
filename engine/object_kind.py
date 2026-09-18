# -*- coding: utf-8 -*-
"""What kind of thing an IDE object is, when its type GUID alone cannot say.

A GVL and a network variable list share a GUID, and so do a textual POU
and a graphical one; the answer is in the object's native XML or in a flag
only some builds expose. classify_object() is the one place that turns an
object into (kind, extension, manager) for both export and import.

Moved out of codesys_managers.py unchanged.
"""
from __future__ import print_function

import os
import tempfile
from engine.ide_tree import is_container_device
from engine.st_text import read_sync_text
from engine.strings import safe_str
from engine.sync_log import log_error, log_warning
from engine.codesys_constants import (
    TYPE_GUIDS,
    XML_TYPES,
    EXPORTABLE_TYPES,
    kind_of,
    sync_direction_of,
)
from engine import unhandled
from engine.ide_read import guid_of, name_of, parent_of


# Distinguishes "property absent" from "property present and falsy" when
# reading an IDE object with a single getattr instead of hasattr-then-read.
_MISSING = object()


def native_xml_of(project, obj, recursive=False):
    """The object's native XML, as text. None when CODESYS wrote nothing.

    There is no API that hands the XML over directly: export_native only
    writes files. So seeing what CODESYS thinks an object is means writing it
    out and reading it back, which is how an NVL is told apart from a GVL, how
    an interface's declaration is recovered, and what compare has to hash for
    an XML-backed object. Three callers each had their own spelling of the
    round trip, their own temp-file name and their own idea of what to do when
    it failed.

    The temp file is named after the object's GUID, so two objects in one run
    cannot land on the same path, and it is removed whether the read worked or
    not. Reading goes through read_sync_text, the repo's one reader, so a BOM
    CODESYS may have written is a byte-order mark here as everywhere else.

    Raises whatever export_native raises: the callers do not agree on what a
    failure means (one has no NVL, one has no declaration, one has nothing to
    compare), so none of them can be answered from in here.
    """
    tmp_path = os.path.join(tempfile.gettempdir(),
                            "cdsint_native_%s.xml" % (guid_of(obj) or "anon")[:8])
    try:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        project.export_native([obj], tmp_path, recursive=recursive)
        if not os.path.exists(tmp_path):
            return None
        return read_sync_text(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def is_nvl(obj, project):
    """
    Detect if a GVL object is actually a Network Variable List (NVL).
    
    CODESYS reports NVLs with the same type GUID as standard GVLs.
    The only way to distinguish them is by exporting to native XML 
    and checking for NVL-specific elements like ListIdentifier or NetworkType.
    
    Returns True if the object is an NVL, False otherwise.
    """
    try:
        if project is None:
            return False
        xml_content = native_xml_of(project, obj)
        if xml_content is None:
            return False
        # NVL XML contains ListIdentifier and/or NetworkType elements
        return 'ListIdentifier' in xml_content or 'NetworkType' in xml_content
    except Exception as e:
        log_warning("Could not check NVL status for " + name_of(obj) + ": " + safe_str(e))
        return False


def is_graphical_pou(obj):
    """
    Detect if a POU uses a graphical language (LD, CFC, FBD) instead of ST/IL.

    CODESYS assigns the same type GUID to all POUs regardless of language.
    The distinguishing factor is that graphical POUs do NOT have a textual
    implementation body — the implementation exists only in the native XML
    (graphical data). ST/IL POUs always have has_textual_implementation=True.

    Returns True if the POU's implementation is graphical (needs XML export),
    False if it is text-based (ST/IL, can be exported as .st).
    """
    try:
        # One read, not two: hasattr() is itself a property read. A sentinel
        # rather than ide_flag() because "missing" and "present but False" mean
        # opposite things here -- missing is the safe textual default, present
        # and False is what identifies a graphical POU.
        value = getattr(obj, 'has_textual_implementation', _MISSING)
        if value is _MISSING:
            # Attribute missing: cannot determine — treat as textual (safe default)
            return False
        return not value
    except Exception as e:
        log_warning("Could not check graphical POU status for " + safe_str(obj.get_name()) + ": " + safe_str(e))
        return False


def classify_object(obj, project):
    """
    Determine the effective export type for a CODESYS object.

    Returns:
        (effective_type, is_xml, should_skip)
        - effective_type: the resolved type GUID (e.g. NVL replaces GVL)
        - is_xml: True if object should be exported/compared as native XML
        - should_skip: True if object should be ignored (property_accessor, task, etc.)

    An object the IDE will not describe comes back as a skip with its name in
    engine/unhandled.py, never as an exception. Reading .type raises when the
    plugin that owns the object is not installed — a project opened in another
    vendor's IDE — and this has five call sites, four of which were inside a
    try/except and one of which was not. The command that went through the
    one that was not lost all 229 objects to a traceback (SPEC D13).
    """
    try:
        obj_type = safe_str(obj.type)
    except Exception as exc:
        unhandled.note(obj, exc)
        log_error("Cannot classify %s: %s" % (unhandled.name_of(obj), safe_str(exc)))
        return "", False, True
    kind = kind_of(obj_type)
    # Normalize alias GUIDs (alternate method/enum variants, ...) onto the
    # kind's primary GUID so downstream comparisons, filenames and the sync
    # cache all see one GUID per kind.
    effective_type = TYPE_GUIDS[kind] if kind else obj_type
    is_xml = False

    # Skip structurally non-exportable kinds: accessor content is folded into
    # the property file; tasks are exported inside task_config's XML.
    if kind in ("property_accessor", "task"):
        return effective_type, False, True

    # Per-kind sync policy from profiles/default.json (e.g. device and
    # device_module are 'disabled' - too unstable for XML sync)
    if kind and sync_direction_of(kind) == "disabled":
        return effective_type, False, True

    # Skip all children of monolithic containers - they are exported as
    # recursive XML with their parent. Prevents duplicate export/sync.
    # Logic for devices: Containers (PLCs) are NOT monolithic, so we don't
    # skip their children (Applications and sub-devices).
    monolithic_kinds = ("alarm_config", "visu_manager", "task_config",
                        "softmotion_pool")
    # obj.parent read once: the guarded form below used to be
    # `hasattr(obj,'parent') and obj.parent` then `obj.parent.type` and then
    # `obj.parent` again for the device check -- four crossings into .NET for
    # one parent, on a function that runs for every skipped object.
    parent = parent_of(obj)
    try:
        parent_type = safe_str(parent.type) if parent else ""
        parent_kind = kind_of(parent_type)
        if parent_kind in monolithic_kinds:
            return effective_type, False, True

        # Device recursion check:
        # If parent is a device, we only skip if the parent IS a monolithic unit.
        if parent_kind == "device":
            if not is_container_device(parent):
                # Parent is functional device (monolithic), so skip children.
                return effective_type, False, True
    except:
        pass

    # Skip per-POU alarm groups/classes — these are auto-generated children of
    # POUs and can't be independently exported. Only alarm groups under the
    # Alarm Configuration tree are valid standalone exports.
    if kind in ("alarm_group", "alarm_class"):
        try:
            if kind_of(safe_str(parent.type)) != "alarm_config":
                return effective_type, False, True
        except:
            pass

    # Skip auto-generated VisualizationStyle objects
    # These are created by CODESYS at multiple locations (Visualization Manager,
    # Application root, project root) and should never be exported/synced.
    if kind == "visu_style":
        return effective_type, False, True

    # NVL detection: GVL that is actually a Network Variable List
    if kind == "gvl":
        try:
            if is_nvl(obj, project):
                effective_type = TYPE_GUIDS["nvl_sender"]
                is_xml = True
        except:
            pass

    # Graphical POU detection (LD, CFC, FBD → XML)
    if not is_xml and kind in ("pou", "action", "method"):
        try:
            if is_graphical_pou(obj):
                is_xml = True
        except:
            pass

    # XML_TYPES are always XML
    if effective_type in XML_TYPES:
        is_xml = True

    # Check if type is exportable at all
    if effective_type not in EXPORTABLE_TYPES and effective_type not in XML_TYPES:
        return effective_type, is_xml, True

    return effective_type, is_xml, False
