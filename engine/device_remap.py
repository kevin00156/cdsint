# -*- coding: utf-8 -*-
"""When the device on disk and the device in the project have different names.

A project opened on another machine may carry a renamed device; paths under
the old name are remapped to the new one for the import rather than
refused.

Moved out of codesys_compare_engine.py unchanged.
"""
from __future__ import print_function

from engine.codesys_constants import TYPE_GUIDS
from engine.ide_tree import find_child_transparent
from engine.strings import safe_str
from engine.sync_log import log_warning


def build_device_remap(project, to_sync):
    """Map an export's device-folder names onto the IDE's actual device names.

    The first path segment of any device-contained object IS the device name
    (see get_container_prefix). When an export made under device 'A' is imported
    into a project whose device is now named 'B', every disk path still begins
    with 'A/...'. find_object_by_path / ensure_folder_path then fail to locate
    'A' under the project root and SILENTLY create a bogus top-level folder 'A',
    nesting every object outside the real device. The objects exist in the
    project (compare's recursive scan sees them) but are invisible under the
    device in the IDE — exactly the "imported but nothing shows up" symptom.

    Returns {leading_segment_lower: real_device_name} for segments that can be
    positively tied to a device, and {} when nothing needs remapping.

    A segment is only remapped when an IDE device already contains a child that
    matches the segment's second path level (e.g. 'Application'). That structural
    confirmation is what distinguishes a renamed device from a legitimate new
    project-global top-level folder (whose second level is a plain file), so we
    never wrongly bury a global pool inside a device.
    """
    try:
        root_children = project.get_children()
    except Exception:
        return {}

    root_names_lower = set()
    devices = []  # (name, obj)
    for child in root_children:
        try:
            root_names_lower.add(safe_str(child.get_name()).lower())
            if safe_str(child.type) == TYPE_GUIDS["device"]:
                devices.append((safe_str(child.get_name()), child))
        except Exception:
            continue

    if not devices:
        return {}

    # Distinct leading segments of the import paths, with the set of second-level
    # segments seen under each (used to structurally confirm a device match).
    leading_display = {}   # lead_lower -> original-cased leading segment
    second_levels = {}     # lead_lower -> set of second-segment names
    for item in to_sync:
        path = item.get("path") or ""
        parts = [p for p in path.replace("\\", "/").split("/") if p]
        if not parts:
            continue
        lead_l = parts[0].lower()
        leading_display.setdefault(lead_l, parts[0])
        if len(parts) >= 2:
            second_levels.setdefault(lead_l, set()).add(parts[1])

    remap = {}
    for lead_l, lead_disp in leading_display.items():
        if lead_l in root_names_lower:
            continue  # already resolves to a real root child — nothing to do

        # Which IDE devices already contain one of this segment's second levels?
        matched = []
        for dev_name, dev_obj in devices:
            for sec in second_levels.get(lead_l, ()):
                if find_child_transparent(dev_obj, sec) is not None:
                    matched.append(dev_name)
                    break

        if len(matched) == 1:
            remap[lead_l] = matched[0]
        elif len(matched) > 1:
            log_warning("Device remap ambiguous for export folder '%s': matches "
                        "IDE devices %s. Leaving paths unchanged." % (lead_disp, matched))
        # No structural match -> leave unmapped (probably a project-global folder,
        # or a device whose Application name also differs). Fail safe.

    return remap


def remap_path_device(path_str, remap):
    """Rewrite the leading device segment of an IDE path using a device remap.

    Only the first segment is touched; the absolute on-disk file path is never
    remapped (the file genuinely lives under the export's device folder).
    """
    if not path_str or not remap:
        return path_str
    parts = path_str.replace("\\", "/").split("/")
    if parts and parts[0].lower() in remap:
        parts[0] = remap[parts[0].lower()]
        return "/".join(parts)
    return path_str


def apply_device_remap(to_sync, remap):
    """Rewrite logical IDE path fields of every import item in place.

    Touches 'path', 'disk_path' and 'ide_path' (all device-prefixed IDE paths),
    but never 'file_path' (the real disk location of the file being read).
    """
    if not remap:
        return
    for item in to_sync:
        for key in ("path", "disk_path", "ide_path"):
            if item.get(key):
                item[key] = remap_path_device(item[key], remap)


def summarize_device_remap(to_sync, remap):
    """Return readable 'OldFolder -> NewDevice' lines for an applied remap.

    The remap is keyed by lowercased segment; this recovers the original-cased
    export folder name from the import paths for display.
    """
    if not remap:
        return []
    old_display = {}
    for item in to_sync:
        parts = [p for p in (item.get("path") or "").replace("\\", "/").split("/") if p]
        if parts:
            key = parts[0].lower()
            if key in remap and key not in old_display:
                old_display[key] = parts[0]
    return ["%s -> %s" % (old_display.get(key, key), new) for key, new in remap.items()]
