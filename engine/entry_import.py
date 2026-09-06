# -*- coding: utf-8 -*-
"""
entry_import.py - Import disk changes into CODESYS IDE

Uses the same comparison engine as entry_compare.py, then automatically
applies all disk-side changes to IDE (equivalent to Compare -> Select All -> Import to IDE).

Also detects new files on disk (e.g. from git pull) not yet tracked in metadata.
"""
from __future__ import print_function

import time

from engine.codesys_utils import (
    safe_str, init_logging, log_info, log_warning,
    reset_interaction_timer, get_interaction_seconds, format_elapsed,
    timed_prompt
)
from engine.codesys_compare_engine import (
    find_all_changes, build_device_remap, summarize_device_remap
)
from engine.import_items import perform_import_items
from engine.backup import create_safety_backup, finalize_sync_operation
from engine.sync_dir import has_st_files
from engine.codesys_online import find_logged_in_applications, logged_in_block_message
from engine import entry, settings, unhandled

from cds.core import dialogs



def import_project(base_dir, values, projects_obj=None):
    """
    Main import entry point.
    Compares disk with IDE and imports all differences automatically.
    Disk is the source of truth — any IDE↔Disk mismatch results in disk winning.
    """
    projects_obj = projects_obj or entry.borrowed(globals(), "projects")
    
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

    # A live PLC login makes every create/move/delete fail inside the IDE, so
    # check before spending a full compare on an import that cannot land.
    online_apps = find_logged_in_applications(projects_obj.primary,
                                             entry.borrowed(globals(), "online"))
    if online_apps:
        block = logged_in_block_message(online_apps)
        print(block)
        log_warning("Import blocked - logged into: " + ", ".join(online_apps))
        system.ui.error(block)
        return entry.result(False, block)

    unhandled.start()
    print("=== Starting Project Import ===")
    print("Importing from: " + base_dir)
    start_time = time.time()
    reset_interaction_timer()
    
    export_xml = values["export_xml"]
    
    # ── Phase 1: Find all changes ──
    print("Comparing IDE with disk...")
    results = find_all_changes(base_dir, projects_obj, export_xml=export_xml)
    
    different = results["different"]
    new_in_ide = results["new_in_ide"]
    new_on_disk = results["new_on_disk"]
    unchanged_count = results["unchanged_count"]
    
    # An object this run could not read never reached the comparison, so
    # nothing claims its .st and the file looks new. Creating an object for
    # it duplicates something the project already has, or -- paired with a
    # real orphan by filename -- moves the wrong one. Export refuses to
    # delete orphans for the same reason and in the same words
    # (entry_export.cleanup_orphaned_files); this is that rule pointed the
    # other way. Updates and deletions still run: each names an IDE object
    # this run did read.
    not_created = []
    withheld = ""
    if unhandled.any_so_far() and new_on_disk:
        not_created = [item["path"] for item in new_on_disk]
        new_on_disk = []
        withheld = ("Not creating %d file(s) this run cannot account for: it "
                    "could not read every object, so some of those files may "
                    "already belong to one of them. %s"
                    % (len(not_created), ", ".join(not_created)))
        print(withheld)
        log_warning(withheld)

    # For import, we care about ANY difference (disk or ide side) — disk wins
    # Also include new files found on disk, and DELETE orphans from IDE
    to_import = []
    
    # Modified objects: disk wins
    for item in different:
        to_import.append(item)
    
    # New files on disk not yet in metadata
    for item in new_on_disk:
        to_import.append({
            "name": item["name"],
            "path": item["path"],
            "file_path": item["file_path"],
            "type": "new",
            "type_guid": "",
            "obj": None
        })
        
    # Orphans in IDE (missing on disk) -> delete
    for item in new_in_ide:
        to_import.append(item)
    
    print("")
    print("Changes found:")
    print("  Modified (IDE<>Disk): " + str(len(different)))
    print("  New on disk: " + str(len(new_on_disk)))
    print("  Missing on disk (delete): " + str(len(new_in_ide)))
    print("  Unchanged: " + str(unchanged_count))
    
    if not to_import:
        elapsed = time.time() - start_time - get_interaction_seconds()
        msg = "No changes to import.\nAll " + str(unchanged_count) + " objects are in sync."
        if withheld:
            msg += "\n" + withheld
        print(msg)
        system.ui.info(msg + "\nTime: " + format_elapsed(elapsed))
        missing = unhandled.names()
        if missing:
            msg += " " + unhandled.summary()
        return entry.result(not missing, msg, updated=0, created=0, moved=0,
                            deleted=0, failed=len(missing),
                            identical=unchanged_count,
                            failed_objects=missing, not_created=not_created)


    # Show what we're about to import
    print("")
    print("Importing " + str(len(to_import)) + " items to IDE:")
    for item in to_import:
        action = "delete" if item.get("is_orphan") else item["type"]
        print("  <- " + item["path"] + " (" + action + ")")
    
    # Detect device-name mismatch so we can warn the user up-front instead of
    # silently nesting everything under a phantom top-level folder.
    device_remap = build_device_remap(projects_obj.primary, to_import)
    remap_lines = summarize_device_remap(to_import, device_remap)
    if remap_lines:
        warn = "Device name mismatch detected.\n\n" \
               "The export was made under a different device name than this " \
               "project's device. Import paths will be remapped onto the real " \
               "device so objects land correctly:\n  " + "\n  ".join(remap_lines)
        print(warn)
        log_warning("Device remap on import: " + "; ".join(remap_lines))

    # Final confirmation before touching the IDE
    from engine.codesys_ui import ask_yes_no
    confirm_msg = "Ready to import {} changes into the IDE.\n\nModified: {}\nNew on disk: {}\nDelete orphans: {}\n\nProceed?".format(
        len(to_import), len(different), len(new_on_disk), len(new_in_ide)
    )
    if remap_lines:
        confirm_msg += "\n\n[!] Device remap (export -> IDE):\n  " + "\n  ".join(remap_lines)
    if not timed_prompt(ask_yes_no, dialogs.CONFIRM_IMPORT, confirm_msg):
        cancelled = "Import cancelled: not confirmed."
        system.ui.warning(cancelled)
        return entry.result(False, cancelled)


    # ── Create timestamped safety backup if enabled ──
    backup_filename = create_safety_backup(base_dir, projects_obj,
                                           to_import, values)
    
    # ── Phase 2: Import all changes ──
    updated, created, failed, deleted, moved = perform_import_items(
        projects_obj.primary, base_dir, to_import,
        entry.borrowed(globals(), "PouType")
    )
    
    # Save and back up BEFORE stopping the clock and announcing completion,
    # so the reported figure covers the whole wait rather than ending at the
    # popup and leaving a project save running behind it.
    finalize_sync_operation(base_dir, projects_obj, values,
                            is_import=True)

    interaction = get_interaction_seconds()
    elapsed = time.time() - start_time - interaction
    elapsed_text = format_elapsed(elapsed, interaction)

    print("")
    print("=== Import Complete ===")
    summary = "Updated: " + str(updated) + ", Created: " + str(created) + ", Moved: " + str(moved) + ", Deleted: " + str(deleted) + ", Failed: " + str(failed) + " (Identical: " + str(unchanged_count) + ")"
    if withheld:
        summary += " -- " + withheld
    print(summary)
    if backup_filename:
        print("Backup created: .project/" + backup_filename)
    print("Time elapsed: " + elapsed_text)

    log_info("Import complete! " + summary + " Time elapsed: " + elapsed_text)

    # Record sync version; metadata file is written in debug mode only
    try:
        from engine.codesys_utils import save_sync_metadata
        save_sync_metadata(base_dir, "import", {
            "updated": updated,
            "created": created,
            "moved": moved,
            "deleted": deleted,
            "failed": failed,
            "identical": unchanged_count
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
    return entry.result(not missing, summary if not missing else
                        summary + " -- " + unhandled.summary(),
                        updated=updated, created=created, moved=moved,
                        deleted=deleted, failed=failed,
                        identical=unchanged_count, failed_objects=missing,
                        not_created=not_created)


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
