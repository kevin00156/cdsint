# -*- coding: utf-8 -*-
"""Applying a change list to the IDE, in the order that makes it work.

codesys_compare_engine.py works out what differs and how to do one object;
this is the pass structure that puts those in the right order and counts what
happened. The order is the whole design, and it used to be one 256-line
function nine levels deep, with the same child lookup written out four times
and the same move written out twice.
"""
from __future__ import print_function

import os

from engine import unhandled
from engine.classify import create_import_managers
from engine.codesys_compare_engine import (
    apply_device_remap, batch_import_native_xmls_with_children,
    build_device_remap, create_new_object, order_st_files_parents_first,
    orphans_their_parent_takes, save_pou_children, summarize_device_remap,
    update_existing_object,
)
from engine.codesys_constants import (
    TYPE_GUIDS, kind_allows_import, kind_of, sync_direction_of,
)
from engine.codesys_utils import (
    ensure_folder_path, find_object_by_path, log_error, log_info, log_warning,
    safe_str,
)
from engine.ide_read import child_named, guid_of, parent_of


class _Tally(object):
    """What an import did, added up across the four passes.

    A small object rather than five integers threaded through five functions:
    the passes each add to two or three of them, and five in and five out of
    every one is a signature nobody can read.
    """

    def __init__(self):
        self.updated = 0
        self.created = 0
        self.failed = 0
        self.deleted = 0
        self.moved = 0

    def as_tuple(self):
        return (self.updated, self.created, self.failed,
                self.deleted, self.moved)


def move_if_needed(item, obj, project):
    """Move obj to where the disk says it now lives. True when it moved.

    The disk path is the truth (PRINCIPLES 5), so a disk path whose folder is
    not the object's current parent means somebody moved the file and the IDE
    has to follow. Written out twice, once for the XML pass and once for the
    ST pass, with the two copies differing only in one word of a log line.
    """
    if not item.get("is_moved"):
        return False
    disk_path = item.get("disk_path")
    if not disk_path or "/" not in disk_path:
        return False

    folder_path = disk_path.rsplit("/", 1)[0]
    target = ensure_folder_path(folder_path, project)
    if not target or target == parent_of(obj):
        return False

    log_info("Moving '%s' in IDE: %s -> %s"
             % (item["name"], item.get("ide_path"), folder_path))
    try:
        obj.move(target)
        return True
    except Exception as exc:
        log_warning("Failed to move %s: %s" % (item["name"], safe_str(exc)))
        return False


def _abs_path(item, base_dir):
    return item.get("file_path") or os.path.join(
        base_dir, item["path"].replace("/", os.sep))


def _is_import_allowed(item):
    """Kinds the profile marks export_only or disabled are never imported,
    overwritten or DELETED: their disk file is a projection for Git to see,
    not a source of truth."""
    kind = kind_of(item.get("type_guid") or "")
    if not kind or kind_allows_import(kind):
        return True
    msg = ("Skipping import of '%s' (%s): sync_direction=%s"
           % (item.get("name"), kind, sync_direction_of(kind)))
    print("  [!] " + msg)
    log_warning(msg)
    return False


def _delete_orphan(item, taken_by_parent, tally):
    """Remove an object whose file is gone. True when the item was dealt with."""
    obj = item.get("obj")
    if not obj:
        return True
    if guid_of(obj) in taken_by_parent:
        # Its POU is on this same list; removing that removes this. Counted,
        # because it will be gone either way.
        tally.deleted += 1
        return True
    try:
        obj.remove()
        tally.deleted += 1
    except Exception as exc:
        log_error("Failed to delete " + item["name"] + ": " + safe_str(exc))
        unhandled.note(item["name"], exc)
        tally.failed += 1
    return True


def _xml_container(item, rel_path, project, tally):
    """Where this XML object belongs, and whether the IDE has it yet.

    Returns (container, is_new). An object already in the tree is imported
    back into its own parent; a new one goes to the folder its path names,
    which is created if the export made it and this project has not.
    """
    obj = item.get("obj") or find_object_by_path(rel_path, project)
    if not obj:
        if "/" in rel_path.replace("\\", "/"):
            parent_path = rel_path.replace("\\", "/").rsplit("/", 1)[0]
            resolved = ensure_folder_path(parent_path, project)
            if resolved:
                return resolved, True
        return project, True

    if move_if_needed(item, obj, project):
        tally.moved += 1
    return parent_of(obj) or project, False


def _sort_items(to_sync, base_dir, project, taken_by_parent, tally):
    """Pass 1: delete the orphans, batch the XML per container, keep the ST.

    XML goes in per-container batches because CODESYS opens one import dialog
    per call, so one call per object would be one dialog per object.
    """
    native_batches = {}
    st_files = []
    for item in to_sync:
        try:
            if not _is_import_allowed(item):
                continue
            if item.get("is_orphan"):
                _delete_orphan(item, taken_by_parent, tally)
                continue

            rel_path = item["path"]
            abs_path = _abs_path(item, base_dir)
            if not os.path.exists(abs_path):
                continue
            if not rel_path.endswith(".xml"):
                st_files.append(item)
                continue

            container, is_new = _xml_container(item, rel_path, project, tally)
            native_batches.setdefault(container, []).append((
                rel_path, abs_path, item.get("name", os.path.basename(rel_path)),
                item.get("type_guid"), is_new))
        except Exception as exc:
            log_error("Failed to process " + item.get("path", "unknown")
                      + ": " + safe_str(exc))
            unhandled.note(item.get("path", "unknown"), exc)
            tally.failed += 1
    return native_batches, st_files


def _save_pou_children(native_batches):
    """Pass 2: remember what hangs off each POU that is about to be replaced.

    A native XML import replaces the POU object, and its methods, actions and
    properties go with it. Keyed by lowercased name, because the object that
    comes back from the import is a different one.
    """
    saved = {}
    for container, items in native_batches.items():
        for _rel_path, _abs_path, name, type_guid, is_new in items:
            if type_guid != TYPE_GUIDS.get("pou") or is_new:
                continue
            existing = child_named(container, name)
            if not existing:
                continue
            children = save_pou_children(existing)
            if children:
                saved[name.lower()] = children
    return saved


def _import_xml(native_batches, import_managers, project, pou_children, name_map,
                tally):
    """Pass 3: import the batches, then let the ST pass find the new POUs."""
    if not native_batches:
        return
    updated, created, failed = batch_import_native_xmls_with_children(
        native_batches, import_managers, project, pou_children)
    tally.updated += updated
    tally.created += created
    tally.failed += failed

    for container, items in native_batches.items():
        for _rel_path, _abs_path, name, type_guid, is_new in items:
            if not is_new or type_guid != TYPE_GUIDS.get("pou"):
                continue
            fresh = child_named(container, name)
            if fresh is None:
                continue
            obj_name = fresh.get_name()
            holders = name_map.setdefault(obj_name, [])
            if fresh not in holders:
                holders.append(fresh)
            log_info("Added new POU to name_map: " + obj_name)


def _create_st(item, rel_path, abs_path, import_managers, name_map,
               folder_cache, project, tally):
    """Make an object the IDE does not have yet, from the file that describes it.

    A file with no matching object means create it (PRINCIPLES 5). A creation
    that returns nothing is a failure with a name, not a number: "it just did
    not import and I do not know why" is the outcome this tool exists to
    avoid (SPEC D13).
    """
    if create_new_object(rel_path, abs_path, import_managers, name_map,
                         folder_cache, project):
        tally.created += 1
        return
    unhandled.note(item.get("path", "unknown"),
                   "could not be created in the IDE")
    tally.failed += 1


def _import_st(st_files, base_dir, import_managers, project, name_map,
               folder_cache, tally):
    """Pass 4: update or create every textual object, parents before children."""
    for item in order_st_files_parents_first(st_files):
        try:
            rel_path = item["path"]
            abs_path = _abs_path(item, base_dir)
            if not os.path.exists(abs_path):
                continue

            obj = item.get("obj") or find_object_by_path(rel_path, project)
            if obj is None:
                _create_st(item, rel_path, abs_path, import_managers, name_map,
                           folder_cache, project, tally)
                continue

            if move_if_needed(item, obj, project):
                tally.moved += 1
            if update_existing_object(obj, rel_path, abs_path, import_managers):
                tally.updated += 1
                log_info("Updated " + item["name"])
        except Exception as exc:
            log_error("Failed to import ST " + item.get("path", "unknown")
                      + ": " + safe_str(exc))
            unhandled.note(item.get("path", "unknown"), exc)
            tally.failed += 1


def _reconcile_device_names(project, to_sync):
    """Rewrite the leading device segment of every path onto the real device.

    An export made under device 'A' imported into a project whose device is
    now 'B' has every path starting 'A/...'. Without this, each object is
    created in a phantom top-level folder named after the old device and never
    appears under the device at all.
    """
    remap = build_device_remap(project, to_sync)
    if not remap:
        return
    for line in summarize_device_remap(to_sync, remap):
        msg = ("Device name mismatch (export -> IDE): %s. "
               "Remapping import paths onto the real device." % line)
        print("  " + msg)
        log_warning(msg)
    apply_device_remap(to_sync, remap)


def perform_import_items(primary_project, base_dir, to_sync, pou_type=None):
    """Import the selected items from disk into the IDE, in four passes.

    The order is the whole design, and it is why this reads as a list rather
    than as one long function:

      1. sort  -- delete orphans, batch the XML per container, keep the ST
      2. save  -- remember the children of every POU about to be replaced
      3. XML   -- import the batches and restore those children
      4. ST    -- update or create the textual objects, now that POUs exist

    Nothing is saved here. The caller finishes with finalize_sync_operation(),
    which owns saving and backup; doing it in both places saved the project
    twice per import.

    Returns (updated, created, failed, deleted, moved).
    """
    tally = _Tally()
    import_managers = create_import_managers(primary_project, pou_type)
    name_map = {}
    folder_cache = {}

    # Worked out before anything is removed, while every object can still be
    # asked who its parent is.
    taken_by_parent = orphans_their_parent_takes(to_sync)
    _reconcile_device_names(primary_project, to_sync)

    native_batches, st_files = _sort_items(
        to_sync, base_dir, primary_project, taken_by_parent, tally)
    pou_children = _save_pou_children(native_batches)
    _import_xml(native_batches, import_managers, primary_project,
                pou_children, name_map, tally)
    _import_st(st_files, base_dir, import_managers, primary_project,
               name_map, folder_cache, tally)
    return tally.as_tuple()
