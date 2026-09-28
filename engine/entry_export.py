from __future__ import print_function

import os
import time

from engine.codesys_constants import sync_direction_of
from engine.sync_cache import build_folder_hashes, load_sync_cache, normalize_path, save_sync_cache
from engine.git_configs import ensure_git_configs
from engine.strings import safe_str
from engine.sync_log import (
    log_info,
    log_warning,
    log_error,
    init_logging,
    reset_interaction_timer,
    get_interaction_seconds,
    format_elapsed,
)
from engine.object_paths import clear_path_caches
from engine.classify import (
    SKIP_SYNC_DIRECTION, collect_accessors, create_import_managers,
    manager_for, resolve_object
)
from engine.backup import finalize_sync_operation
from engine.device_pass import export_devices
from engine.orphan_sweep import cleanup_orphaned_files
from engine import entry, settings, unhandled


def _claim_unwritten(decided, exported_paths):
    """Keep the file of an object this run does not write off the orphan list.

    An import_only kind, or an XML kind with export_xml off, still has an
    object in the project and usually a file somebody committed; left
    unclaimed, the orphan sweep deletes it. A kind with no path has no file
    to keep.
    """
    if decided.skip_reason == SKIP_SYNC_DIRECTION:
        log_info("Skipping export of %s (sync_direction=%s)"
                 % (decided.rel_path,
                    sync_direction_of(decided.effective_type)))
    if decided.rel_path:
        exported_paths.add(decided.rel_path)


def _carry_entry(cache_data, norm_path, new_cache):
    """Start this object's entry from the last sync's, so an object this run
    skips or leaves pending keeps what the dirty-file guard reads (SPEC 6.1).
    A manager that writes the file replaces it."""
    try:
        cached_obj = cache_data.get('objects', {}).get(norm_path)
    except (AttributeError, TypeError):
        return  # A cache file of the wrong shape is no cache.
    if norm_path and cached_obj:
        new_cache[norm_path] = cached_obj


def _save_cache(export_dir, new_cache, context):
    """Calculate folder hashes (Merkle Tree) and save the updated cache."""
    if not new_cache:
        return
    # build_folder_hashes expects a dict of {path: ide_hash}
    just_hashes = {path: record.get('ide_hash') for path, record in new_cache.items()}
    folder_hashes = build_folder_hashes(just_hashes)
    save_sync_cache(export_dir, new_cache, folder_hashes, context.get('new_types'))
    log_info("Saved updated sync cache with {} objects and {} folders.".format(
        len(new_cache), len(folder_hashes)))


def export_project(export_dir, values, projects_obj=None):
    """Export all project objects to folder structure with metadata"""
    
    # Resolving projects object
    projects_obj = projects_obj or entry.borrowed(globals(), "projects")
    
    if projects_obj is None or not projects_obj.primary:
        msg = "Error: 'projects' object not found or no project open."
        try:
            system.ui.error(msg)
        except NameError:
            print("Error:", msg)
        return entry.result(False, msg)

    # One read of the open project, handed to everything below it: the
    # managers, the classifier and the content readers all need it, and each
    # of them used to go looking for it on its own.
    project = projects_obj.primary

    # Create export directory
    if not os.path.exists(export_dir):
        os.makedirs(export_dir)
    
    # Ensure Git config files exist
    ensure_git_configs(export_dir)
    
    unhandled.start()
    print("=== Starting Project Export ===")
    start_time = time.time()
    reset_interaction_timer()
    print("Export directory: " + export_dir)
    
    # Flags and tracking
    export_xml = values["export_xml"]
    backup_binary = values["backup_binary"]
    exported_paths = set()  # For orphan tracking
    
    # The binary backup runs once, at the end, from finalize_sync_operation().
    # It used to also run here, before the export: both write the same
    # non-timestamped filename and export only READS the project, so the two
    # copies were byte-identical and the second simply overwrote the first --
    # two CODESYS saves and two full-file copies (9.7 MB on this project) for
    # one export.
    if backup_binary:
        print("Binary backup enabled (written after export).")
    else:
        print("Binary backup disabled (skipping .project copy).")

    # Get all objects recursively. Paths are memoized per ancestor, so start
    # from a clean slate in case an earlier operation moved objects around.
    clear_path_caches()
    all_objects = projects_obj.primary.get_children(recursive=True)
    print("Found " + str(len(all_objects)) + " total objects")
    
    exported_new = 0
    exported_updated = 0
    exported_identical = 0
    exported_failed = 0
    pending_import = []      # edited on disk, not imported yet (SPEC 6.1)
    
    # Property accessors collected dynamically during main loop
    property_accessors = {}
    
    # Initialize managers
    managers = create_import_managers(project)
    
    # Load sync cache for fast-export skipping
    cache_data = load_sync_cache(export_dir)
    new_cache = {}
    if cache_data and cache_data.get('objects'):
        log_info("Sync cache loaded! Enabling accelerated export (Merkle Tree skip).")
    
    context = {
        'export_dir': export_dir,
        'export_xml': export_xml,
        'property_accessors': property_accessors,
        'exported_paths': exported_paths,
        'cache_data': cache_data,
        'new_cache': new_cache,
        'new_types': {}
    }

    # Every object, in the order the tree gave them
    for obj in all_objects:
        try:
            obj_guid = safe_str(obj.guid)
            decided = resolve_object(obj, obj_guid, cache_data.get('types', {}),
                                     export_xml, project)
            effective_type = decided.effective_type
            is_xml = decided.is_xml
            rel_path = decided.rel_path

            # Stored for the next run whatever was decided, skips included:
            # a "no path here" answer is worth as much as a path next time.
            context['new_types'][obj_guid] = (effective_type, is_xml, rel_path)

            norm_path = normalize_path(rel_path) if rel_path else None
            
            collect_accessors(obj, obj_guid, effective_type,
                              context['property_accessors'])

            _carry_entry(cache_data, norm_path, new_cache)

            if decided.skip_reason:
                _claim_unwritten(decided, exported_paths)
                continue

            manager = manager_for(managers, effective_type, is_xml)
            wrote = manager.export(obj, effective_type, rel_path, context)
            if wrote == "new":
                exported_new += 1
            elif wrote == "updated":
                exported_updated += 1
            elif wrote == "identical":
                exported_identical += 1
            elif wrote == "pending":
                # Left alone on purpose: the file holds an edit nobody has
                # imported yet (SPEC 6.1). Not a failure of this object, so
                # it stays out of the unhandled register and gets its own
                # list -- what the reader has to do about it is different.
                pending_import.append(rel_path)
                log_warning("Not overwriting " + rel_path + ": it has been "
                            "edited on disk since the last sync. Import it "
                            "first, or delete it and export again.")

        except Exception as e:
            exported_failed += 1
            unhandled.note(obj, e)
            log_error("Error exporting " + unhandled.name_of(obj) + ": " + safe_str(e))

    # The EtherCAT devices are not objects of the sync above (SPEC 6.10).
    pending_import.extend(export_devices(project, export_dir, context, managers))
    # A file no object claims that the last sync did not leave that way is
    # somebody's work, so it waits for import rather than being deleted.
    removed_count, unsynced = cleanup_orphaned_files(
        export_dir, exported_paths, values["auto_delete_orphans"],
        cache_data.get('objects', {}), new_cache)
    pending_import.extend(unsynced)
    _save_cache(export_dir, new_cache, context)

    # Save and back up BEFORE stopping the clock and announcing completion.
    # This step saves the project and, when enabled, copies the whole .project
    # binary; running it after the timer meant the reported figure excluded
    # the part of the wait that came after the popup said "complete".
    save_error = finalize_sync_operation(export_dir, projects_obj, values,
                                         is_import=False)

    print("=== Export Complete ===")
    interaction_time = get_interaction_seconds()
    elapsed_time = time.time() - start_time - interaction_time
    elapsed_text = format_elapsed(elapsed_time, interaction_time)
    print("New: " + str(exported_new) + ", Updated: " + str(exported_updated) + ", Identical: " + str(exported_identical) + ", Removed: " + str(removed_count))
    print("Time elapsed: " + elapsed_text)
    print("Completed at: " + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))

    exported_total = exported_new + exported_updated + exported_identical
    summary = "Updated: " + str(exported_updated) + ", Created: " + str(exported_new) + ", Removed: " + str(removed_count) + ", Failed: " + str(exported_failed) + " (Identical: " + str(exported_identical) + ")"
    if pending_import:
        summary += ", Waiting to be imported: " + ", ".join(pending_import)
    if save_error:
        summary += (" -- the export itself finished; only the IDE project"
                    " was not saved: " + save_error)
    log_info("Export complete! " + summary + " Time elapsed: " + elapsed_text)

    # Record sync version; metadata file is written in debug mode only
    from engine.sync_log import save_sync_metadata
    save_sync_metadata(export_dir, "export", {
        "new": exported_new,
        "updated": exported_updated,
        "identical": exported_identical,
        "removed": removed_count,
        "failed": exported_failed,
        "total": exported_total
    }, elapsed_time)

    # Show completion notification
    try:
        system.ui.info("Export complete!\n\n" + summary + "\nLocation: " + export_dir + "\nTime elapsed: " + elapsed_text)
    except NameError:
        print("Export complete!\n" + summary + "\nLocation: " + export_dir + "\nTime elapsed: " + elapsed_text)

    # Disk is the source of truth (SPEC target 1), so an export that left
    # objects behind is not a finished export, however many it did write.
    # It still wrote all the others: giving up on the first bad object
    # would be worse than reporting the ones that did not make it.
    #
    # Two ways to be left behind, and they need different things from the
    # reader: an object this run could not handle (D13) wants somebody to
    # find out why, and a file holding an unimported edit (6.1) wants an
    # import. Both mean the disk does not match the IDE, so both mean not ok.
    missing = unhandled.names()
    return entry.result(not missing and not pending_import and not save_error,
                        summary if not missing else
                        summary + " -- " + unhandled.summary(),
                        new=exported_new, updated=exported_updated,
                        identical=exported_identical, removed=removed_count,
                        failed=len(missing), total=exported_total,
                        failed_objects=missing,
                        pending_import=pending_import)


def main():
    # A project that has never been synced gets asked where to sync to,
    # rather than being told to go and run a menu entry that no longer
    # exists (SPEC 6.7). With nobody at the keyboard the dialog is refused,
    # not guessed at: cds/ide/silent.py turns it into needs_input.
    values, base_dir, error = settings.prepare_asking(globals())
    if error:
        try:
            system.ui.warning(error)
        except NameError:
            print("Error:", error)
        return entry.result(False, error)

    init_logging(base_dir, values["debug"])
    return export_project(base_dir, values)


if __name__ == "__main__":
    main()