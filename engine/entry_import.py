# -*- coding: utf-8 -*-
"""
entry_import.py - Import disk changes into CODESYS IDE

Uses the same comparison engine as entry_compare.py, then automatically
applies all disk-side changes to IDE (equivalent to Compare -> Select All -> Import to IDE).

Also detects new files on disk (e.g. from git pull) not yet tracked in metadata.

import_project reads as the steps of one import: refuse what cannot land,
plan from the comparison, confirm, back up, apply, report. The steps were
one 228-line function; they were split out of it unchanged.
"""
from __future__ import print_function

import os
import time

from engine.ide_hash import get_quick_ide_hash
from engine.strings import safe_str
from engine.sync_cache import (
    file_signature, load_sync_cache, normalize_path, save_sync_cache)
from engine.sync_log import (
    init_logging,
    log_info,
    log_warning,
    reset_interaction_timer,
    get_interaction_seconds,
    format_elapsed,
    timed_prompt,
)
from engine import device_changes
from engine.device_pass import find_changes
from engine.device_remap import build_device_remap, summarize_device_remap
from engine.import_items import perform_import_items
from engine.backup import create_safety_backup, finalize_sync_operation
from engine.sync_dir import has_st_files
from engine.codesys_online import find_logged_in_applications, logged_in_block_message
from engine import entry, settings, unhandled

from cds.core import dialogs


class _Plan(object):
    """What this import is going to do, worked out from the comparison."""

    def __init__(self, results):
        self.different = results["different"]
        self.new_in_ide = results["new_in_ide"]
        self.new_on_disk = results["new_on_disk"]
        self.moved = results["moved"]
        self.unchanged_count = results["unchanged_count"]
        self.not_created = []
        self.withheld = ""
        self.items = []


def import_project(base_dir, values, projects_obj=None):
    """
    Main import entry point.
    Compares disk with IDE and imports all differences automatically.
    Disk is the source of truth — any IDE↔Disk mismatch results in disk winning.
    """
    projects_obj = projects_obj or entry.borrowed(globals(), "projects")
    refused = _preflight(base_dir, projects_obj)
    if refused is not None:
        return refused

    print("=== Starting Project Import ===")
    print("Importing from: " + base_dir)
    start_time = time.time()
    reset_interaction_timer()

    print("Comparing IDE with disk...")
    plan = _plan(find_changes(base_dir, projects_obj, values))
    if not plan.items:
        return _nothing_to_import(plan, start_time)

    refused = _confirm(plan, projects_obj)
    if refused is not None:
        return refused

    backup_filename, backup_error = create_safety_backup(
        base_dir, projects_obj, plan.items, values)
    if backup_error:
        refused = "Safety backup failed, nothing was imported: " + backup_error
        system.ui.warning(refused)
        return entry.result(False, refused)

    counts = perform_import_items(
        projects_obj.primary, base_dir, plan.items,
        entry.borrowed(globals(), "PouType")
    )
    _record_cache(base_dir, plan.items)

    # Save and back up BEFORE stopping the clock and announcing completion,
    # so the reported figure covers the whole wait rather than ending at the
    # popup and leaving a project save running behind it.
    save_error = finalize_sync_operation(base_dir, projects_obj, values,
                                         is_import=True)
    return _report(plan, counts, save_error, backup_filename, start_time,
                   base_dir, projects_obj)


def _preflight(base_dir, projects_obj):
    """The refusals that come before any comparison. None when it may go on."""
    if projects_obj is None or not projects_obj.primary:
        msg = "Error: 'projects' object not found or no project open."
        system.ui.error(msg)
        return entry.result(False, msg)

    # Disk wins, so this folder is the answer to "what should the project
    # contain". A folder with no .st in it is not the answer "nothing": it is
    # a folder nobody has exported to, or the wrong folder. Taken literally it
    # deletes every object in the project, which is what a headless verify
    # pointed at a fresh --sync-dir did to 178 of 229 objects. A missing
    # source of truth is refused, the same way a live PLC login is, rather
    # than measured against a threshold (SPEC 4.2).
    if not has_st_files(base_dir):
        refused = ("No .st files in the sync folder: " + base_dir + "\n\n"
                   "Refusing to import. Disk wins, so importing from an empty "
                   "folder would delete every object in the project.\n\n"
                   "Run export first, or point sync_folder in the project's "
                   "settings file (--sync-dir in the --project form) at the "
                   "folder that holds the .st files.")
        print(refused)
        system.ui.error(refused)
        return entry.result(False, refused)

    # Before the pre-flight, not after: the pre-flight walks the device tree
    # and records every node that will not answer (SPEC D13), and starting the
    # register afterwards threw those entries away. A device whose plugin is
    # missing then looked exactly like a device with nothing logged into it,
    # and the import went ahead to fail object by object with nothing in the
    # log pointing at why.
    unhandled.start()

    # A live PLC login makes every create/move/delete fail inside the IDE, so
    # check before spending a full compare on an import that cannot land.
    online_apps = find_logged_in_applications(projects_obj.primary,
                                             entry.borrowed(globals(), "online"))
    if online_apps:
        block = logged_in_block_message(online_apps)
        print(block)
        log_warning("Import blocked - logged into: " + ", ".join(online_apps))
        system.ui.error(block)
        return entry.result(False, block, failed_objects=unhandled.names())
    return None


def _plan(results):
    """Every difference, turned into an item for perform_import_items."""
    plan = _Plan(results)

    # An object this run could not read never reached the comparison, so
    # nothing claims its .st and the file looks new. Creating an object for
    # it duplicates something the project already has, or -- paired with a
    # real orphan by filename -- moves the wrong one. Export refuses to
    # delete orphans for the same reason and in the same words
    # (engine/orphan_sweep.py); this is that rule pointed the
    # other way. Updates and deletions still run: each names an IDE object
    # this run did read.
    if unhandled.any_so_far() and (plan.new_on_disk or plan.moved):
        plan.not_created = ([item["path"] for item in plan.new_on_disk]
                            + [move["disk_path"] for move in plan.moved])
        plan.new_on_disk, plan.moved = [], []
        plan.withheld = ("Not creating or moving objects for %d file(s) this "
                         "run cannot account for: it "
                         "could not read every object, so some of those files may "
                         "already belong to one of them. %s"
                         % (len(plan.not_created), ", ".join(plan.not_created)))
        print(plan.withheld)
        log_warning(plan.withheld)

    # For import, we care about ANY difference (disk or ide side) — disk wins.
    # Modified objects, objects whose file moved, then new files on disk not
    # yet in metadata, then the objects whose file is gone, which are deleted
    # from the IDE.
    plan.items.extend(plan.different)
    for move in plan.moved:
        plan.items.append(dict(move, path=move["disk_path"], type="moved",
                               is_moved=True))
    for item in plan.new_on_disk:
        plan.items.append({
            "name": item["name"],
            "path": item["path"],
            "file_path": item["file_path"],
            "type": "new",
            "type_guid": "",
            "obj": None, "refused": item.get("refused"), "device_pass": item.get("device_pass")
        })
    plan.items.extend(plan.new_in_ide)

    print("")
    print("Changes found:")
    print("  Modified (IDE<>Disk): " + str(len(plan.different)))
    print("  Moved on disk: " + str(len(plan.moved)))
    print("  New on disk: " + str(len(plan.new_on_disk)))
    print("  Missing on disk (delete): " + str(len(plan.new_in_ide)))
    print("  Unchanged: " + str(plan.unchanged_count))
    return plan


def _nothing_to_import(plan, start_time):
    elapsed = time.time() - start_time - get_interaction_seconds()
    msg = "No changes to import.\nAll " + str(plan.unchanged_count) + " objects are in sync."
    if plan.withheld:
        msg += "\n" + plan.withheld
    print(msg)
    system.ui.info(msg + "\nTime: " + format_elapsed(elapsed))
    missing = unhandled.names()
    if missing:
        msg += " " + unhandled.summary()
    return entry.result(not missing, msg, updated=0, created=0, moved=0,
                        deleted=0, failed=len(missing),
                        identical=plan.unchanged_count,
                        failed_objects=missing, not_created=plan.not_created)


def _confirm(plan, projects_obj):
    """Show what is about to change and ask. None when confirmed."""
    print("")
    print("Importing " + str(len(plan.items)) + " items to IDE:")
    for item in plan.items:
        action = "delete" if item.get("is_orphan") else item["type"]
        print("  <- " + item["path"] + " (" + action + ")")

    # Detect device-name mismatch so we can warn the user up-front instead of
    # silently nesting everything under a phantom top-level folder.
    device_remap = build_device_remap(projects_obj.primary, plan.items)
    remap_lines = summarize_device_remap(plan.items, device_remap)
    if remap_lines:
        warn = "Device name mismatch detected.\n\n" \
               "The export was made under a different device name than this " \
               "project's device. Import paths will be remapped onto the real " \
               "device so objects land correctly:\n  " + "\n  ".join(remap_lines)
        print(warn)
        log_warning("Device remap on import: " + "; ".join(remap_lines))

    from engine.codesys_ui import ask_yes_no
    confirm_msg = "Ready to import {} changes into the IDE.\n\nModified: {}\nMoved: {}\nNew on disk: {}\nDelete orphans: {}\n\nProceed?".format(
        len(plan.items), len(plan.different), len(plan.moved),
        len(plan.new_on_disk), len(plan.new_in_ide)
    )
    if remap_lines:
        confirm_msg += "\n\n[!] Device remap (export -> IDE):\n  " + "\n  ".join(remap_lines)
    if not timed_prompt(ask_yes_no, dialogs.CONFIRM_IMPORT, confirm_msg):
        cancelled = "Import cancelled: not confirmed."
        system.ui.warning(cancelled)
        return entry.result(False, cancelled)
    return None


def _record_cache(base_dir, items):
    """Write down that each file that landed now matches its object.

    The compare this import started from saved the cache before anything
    was applied, so a file edited on disk and imported kept the entry from
    before the edit. The next export read its signature as "edited since the
    last sync" and left it pending; an import after that wrote the file back
    over whatever had been changed in the IDE meanwhile (SPEC 6.1). The entry
    has the shape export writes. A failed item keeps its old entry.
    """
    cache = load_sync_cache(base_dir)
    for item in items:
        obj = item.get("landed")
        if obj is None:
            continue
        abs_path = item.get("file_path") or os.path.join(
            base_dir, item["path"].replace("/", os.sep))
        try:
            disk_mtime, disk_size = file_signature(abs_path)
        except OSError:
            continue
        rel_path = os.path.relpath(abs_path, base_dir)
        cache["objects"][normalize_path(rel_path)] = {
            "ide_hash": get_quick_ide_hash(obj, abs_path.endswith(".xml")),
            "disk_mtime": disk_mtime, "disk_size": disk_size}
    save_sync_cache(base_dir, cache["objects"], cache["folders"],
                    cache["types"])


def _report(plan, counts, save_error, backup_filename, start_time, base_dir,
            projects_obj):
    """Say what the import did, on screen and in the result."""
    updated, created, failed, deleted, moved = counts
    interaction = get_interaction_seconds()
    elapsed = time.time() - start_time - interaction
    elapsed_text = format_elapsed(elapsed, interaction)

    print("")
    print("=== Import Complete ===")
    summary = "Updated: " + str(updated) + ", Created: " + str(created) + ", Moved: " + str(moved) + ", Deleted: " + str(deleted) + ", Failed: " + str(failed) + " (Identical: " + str(plan.unchanged_count) + ")"
    if plan.withheld:
        summary += " -- " + plan.withheld
    if save_error:
        summary += " -- but the project was not saved: " + save_error
    print(summary)
    if backup_filename:
        print("Backup created: .project/" + backup_filename)
    print("Time elapsed: " + elapsed_text)

    log_info("Import complete! " + summary + " Time elapsed: " + elapsed_text)

    # Record sync version; metadata file is written in debug mode only
    try:
        from engine.sync_log import save_sync_metadata
        save_sync_metadata(base_dir, "import", {
            "updated": updated,
            "created": created,
            "moved": moved,
            "deleted": deleted,
            "failed": failed,
            "identical": plan.unchanged_count
        }, elapsed)
    except Exception as e:
        log_warning("Failed to update metadata: " + safe_str(e))

    try:
        message = "Import complete!\n\n" + summary + "\nTime: " + elapsed_text
        if backup_filename:
            message += "\n\nBackup created: .project/" + backup_filename
        system.ui.info(message)
    except NameError:
        print("Import complete!\n" + summary)

    # Disk is the source of truth (SPEC target 1), so an import that left
    # items on disk is not a finished import. The rest of them still landed:
    # stopping at the first one would be worse than naming the ones that
    # did not.
    missing = unhandled.names()
    return entry.result(not missing and not save_error, summary if not missing
                        else summary + " -- " + unhandled.summary(),
                        updated=updated, created=created, moved=moved,
                        deleted=deleted, failed=failed,
                        identical=plan.unchanged_count, failed_objects=missing,
                        not_created=plan.not_created,
                        **device_changes.report(projects_obj.primary))


def main():
    # Same first-run setup as export (SPEC 6.7); see entry_export.main.
    values, base_dir, error = settings.prepare_asking(globals())
    if error:
        system.ui.warning(error)
        return entry.result(False, error)

    init_logging(base_dir, values["debug"])
    return import_project(base_dir, values)


if __name__ == "__main__":
    main()
