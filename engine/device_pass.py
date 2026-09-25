# -*- coding: utf-8 -*-
"""The EtherCAT devices, synchronised beside the object sync (SPEC 6.10).

`device` and `device_module` stay disabled for the object sync: importing
their native XML duplicates the tree (docs/ethercat-research.md 2.2). The
devices under an EtherCAT master get this pass instead: one `.device` file
each, found by walking the device tree, compared, exported and imported
through engine/device_params.py. The suffix is deliberately not a sync suffix,
so the object sync never sees these files; this pass owns them.
"""
from __future__ import print_function

import os

from cds.core import device_text
from engine import device_changes, device_params, unhandled
from engine.change_detect import find_all_changes
from engine.managers_device import NOT_CREATED
from engine.codesys_constants import TYPE_GUIDS, kind_of
from engine.ide_read import children_of
from engine.st_text import read_sync_text
from engine.strings import clean_filename, safe_str
from engine.sync_cache import load_sync_cache, save_sync_cache
from engine.sync_log import log_info

MASTER_TYPE = 64
REFUSED = ("not applied: the settings file does not allow device settings "
           "(add \"devices\": true to it; SPEC 6.10)")


def _is_master(device):
    try:
        return device.get_device_identification().type == MASTER_TYPE
    except Exception:
        # A device that will not say what it is is not taken for a master.
        return False


def ethercat_devices(project):
    """(device, rel_path) for each EtherCAT master and everything below it,
    parents first, laid out like the device tree."""
    found = []
    stack = [(child, [], False) for child in reversed(children_of(project))]
    while stack:
        node, parts, under = stack.pop()
        if not getattr(node, "is_device", False):
            continue
        parts = parts + [clean_filename(safe_str(node.get_name()))]
        under = under or _is_master(node)
        if under:
            found.append((node, "/".join(parts) + device_text.SUFFIX))
        stack.extend((c, parts, under) for c in reversed(children_of(node)))
    return found


def _device_files(base_dir):
    """{lower-case rel path: rel path as on disk}. Windows keeps a file's old
    case when export rewrites it for a device renamed only in case, so the
    match is case-insensitive, as the file system's is."""
    found = {}
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")
                   and d != "__pycache__"]
        for name in files:
            if name.endswith(device_text.SUFFIX):
                rel = os.path.relpath(os.path.join(root, name), base_dir)
                rel = rel.replace(os.sep, "/")
                found[rel.lower()] = rel
    return found


def _item(device, rel):
    return {"name": safe_str(device.get_name()), "path": rel,
            "type": "device", "obj": device, "device_pass": True,
            "type_guid": TYPE_GUIDS[kind_of(safe_str(device.type)) or "device"]}


def _compare_one(device, rel, base_dir, results, allowed):
    ide_text = device_params.render(device)
    disk_text = read_sync_text(os.path.join(base_dir, rel.replace("/", os.sep)))
    if device_text.same(ide_text, disk_text):
        results["unchanged_count"] += 1
        return
    item = _item(device, rel)
    item.update({"ide_content": ide_text, "disk_content": disk_text,
                 "ide_attrs": {}, "disk_attrs": {}})
    if not allowed:
        item["refused"] = REFUSED
    results["different"].append(item)


def with_device_changes(results, base_dir, project, values):
    """find_all_changes' results, with the devices' differences added.

    The object sync sees `.device` files (they are sync files, so the orphan
    sweep offers stale ones), but they are this pass's to report, so its
    entries for them are replaced by this pass's. A device with no file is
    not an orphan to import: import never deletes a device, and listing it
    made every import of an older sync folder offer 81 deletions it would
    not do. A file with no device is refused by path whatever else its path
    resolves to (SPEC 6.10).
    """
    device_changes.start()
    results["new_on_disk"] = [i for i in results["new_on_disk"]
                              if not i["path"].endswith(device_text.SUFFIX)]
    allowed = bool(values.get("devices"))
    on_disk = _device_files(base_dir)
    missing = []
    for device, rel in ethercat_devices(project):
        found = on_disk.pop(rel.lower(), None)
        if found is None:
            missing.append(rel)
            continue
        try:
            _compare_one(device, found, base_dir, results, allowed)
        except Exception as exc:
            unhandled.note(device, exc)
    if missing:
        log_info("%d device(s) have no file yet; export writes them: %s"
                 % (len(missing), ", ".join(missing[:5])))
    for rel in sorted(on_disk.values()):
        results["new_on_disk"].append({
            "name": os.path.splitext(os.path.basename(rel))[0], "path": rel,
            "file_path": os.path.join(base_dir, rel.replace("/", os.sep)),
            "device_pass": True, "refused": NOT_CREATED % rel})
    return results


def keep_device_cache(base_dir, before):
    """Put back the cache entries of device files a compare dropped.

    find_all_changes saves only the object sync's entries, and without its
    entry a device file loses the dirty-file guard (SPEC 6.1): the next
    export overwrote an edit nobody had imported.
    """
    cache = load_sync_cache(base_dir)
    objects = cache["objects"]
    lost = dict((path, entry) for path, entry in before.items()
                if path.endswith(device_text.SUFFIX) and path not in objects)
    if lost:
        objects.update(lost)
        save_sync_cache(base_dir, objects, cache["folders"], cache["types"])


def find_changes(base_dir, projects_obj, values):
    """The object sync's changes and the devices', in one result."""
    before = load_sync_cache(base_dir)["objects"]
    results = find_all_changes(base_dir, projects_obj,
                               export_xml=values["export_xml"])
    keep_device_cache(base_dir, before)
    return with_device_changes(results, base_dir, projects_obj.primary, values)


def export_devices(project, export_dir, context, managers):
    """Write every device's file. The paths left alone because they hold an
    edit nobody imported (SPEC 6.1)."""
    pending = []
    manager = managers[TYPE_GUIDS["device"]]
    cached = (context.get("cache_data") or {}).get("objects", {})
    for device, rel in ethercat_devices(project):
        # Carried first, as export_project does for objects: a file left
        # pending writes no entry, and without the old one the next export
        # overwrote the edit (measured on 3.5.21.40).
        if rel in cached:
            context["new_cache"][rel] = cached[rel]
        try:
            if manager.export(device, None, rel, context) == "pending":
                pending.append(rel)
        except Exception as exc:
            unhandled.note(device, exc)
    return pending
