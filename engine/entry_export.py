import os
import sys
import time
import codecs
import json

from cds.core import props
from engine.codesys_constants import (
    IMPL_MARKER, TYPE_GUIDS, EXPORTABLE_TYPES, XML_TYPES, FORBIDDEN_CHARS, RESERVED_FILES,
    SCRIPT_VERSION, kind_allows_export, sync_direction_of
)
from engine.codesys_utils import (
    safe_str, clean_filename, load_base_dir,
    calculate_hash, format_st_content,
    log_info, log_warning, log_error,
    init_logging, format_property_content,
    resolve_projects, set_application_count_flag, ensure_git_configs,
    get_quick_ide_hash, load_sync_cache, save_sync_cache, build_folder_hashes,
    normalize_path, finalize_sync_operation, reset_interaction_timer,
    get_interaction_seconds, format_elapsed
)
from engine.codesys_managers import (
    FolderManager, POUManager, PropertyManager, NativeManager, ConfigManager,
    get_object_path, collect_property_accessors, is_nvl, is_graphical_pou,
    classify_object, build_expected_path, clear_path_caches
)
from engine.codesys_compare_engine import create_import_managers
from engine import entry, unhandled

# Shared constants and utilities imported from modules


def cleanup_orphaned_files(export_dir, current_objects):
    """
    Find and optionally delete files in export_dir that are not in current_objects.
    """
    orphaned_items = []
    
    # We'll collect everything first to show a preview
    for root, dirs, files in os.walk(export_dir):
        # Skip hidden dirs (including .diff, .git, .project etc.)
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        
        # Calculate relative path from export_dir
        rel_root = os.path.relpath(root, export_dir)
        if rel_root == ".":
            rel_root = ""
            
        # Check files
        for f in files:
            # Skip reserved files and folders
            # Skip files starting with dot
            if f.startswith("."):
                continue

            # Only consider our export types to be safe
            if not (f.endswith(".st") or f.endswith(".xml")):
                continue
                
            rel_path = os.path.join(rel_root, f).replace("\\", "/")
            if rel_path not in current_objects:
                orphaned_items.append(rel_path)

    if not orphaned_items:
        return 0

    # An object this run could not classify has no path, so its .st file looks
    # like an orphan and deleting it would throw away a file the project still
    # needs. The run does not know which files those are -- that is what "could
    # not classify" means -- so it deletes none of them.
    if unhandled.any_so_far():
        print("Orphan cleanup skipped: " + unhandled.summary())
        log_warning("Not deleting %d orphan(s): this run could not classify "
                    "every object, so some of them may belong to one of those."
                    % len(orphaned_items))
        return 0

    # Check for auto-delete property
    try:
        from engine.codesys_utils import get_project_prop
        auto_delete = get_project_prop(props.AUTO_DELETE_ORPHANS, False)
    except Exception:
        # Reading a project property is an IDE call and can raise anything.
        # Not knowing means not deleting.
        auto_delete = False

    if auto_delete:
        choice_idx = 0 # Delete
    else:
        # Prompt user
        message = "The following files exist in the export directory but are NOT in the CODESYS project (orphans):\n\n"
        # Show first 15 files as preview
        for item in orphaned_items[:15]:
            message += "- " + item + "\n"
        if len(orphaned_items) > 15:
            message += "... and " + str(len(orphaned_items) - 15) + " more.\n"
        
        message += "\nWould you like to delete these orphaned files?"
        
        # buttons: Delete (Yes), Ignore (No)
        from engine.codesys_ui import ask_yes_no
        from engine.codesys_utils import timed_prompt
        if timed_prompt(ask_yes_no, "Delete Orphaned Files?", message):
            choice_idx = 0 # Delete
        else:
            choice_idx = 1 # Ignore
    
    removed_count = 0
    if choice_idx == 0: # Delete
        print("Cleaning up orphaned files...")
        for rel_path in orphaned_items:
            full_path = os.path.join(export_dir, rel_path.replace("/", os.sep))
            try:
                if os.path.exists(full_path):
                    os.remove(full_path)
                    removed_count += 1
                    print("Deleted: " + rel_path)
            except Exception as e:
                print("Error deleting " + rel_path + ": " + safe_str(e))
        
        # Now clean up empty directories
        # Use topdown=False to delete subdirectories before parents
        for root, dirs, files in os.walk(export_dir, topdown=False):
            # Also skip hidden dirs here
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            
            rel_root = os.path.relpath(root, export_dir)
            if rel_root == "." or not rel_root:
                continue
            
            rel_path = rel_root.replace("\\", "/")
            
            # Check if this folder or any of its children should exist
            folder_needed = False
            for obj_path in current_objects:
                if obj_path.startswith(rel_path + "/"):
                    folder_needed = True
                    break
            
            if not folder_needed and rel_path not in current_objects:
                # If directory is empty, delete it
                try:
                    if not os.listdir(root):
                        os.rmdir(root)
                        print("Deleted empty folder: " + rel_path)
                except OSError:
                    pass  # Not empty, or gone already. Either way, leave it.
        return removed_count
    elif choice_idx == 1: # Ignore
        print("Orphaned files ignored.")
        return 0
    else: # Cancel
        print("Export cancelled during cleanup.")
        return None





def export_project(export_dir, projects_obj=None):
    """Export all project objects to folder structure with metadata"""
    
    # Resolving projects object
    projects_obj = resolve_projects(projects_obj, globals())
    
    if projects_obj is None or not projects_obj.primary:
        msg = "Error: 'projects' object not found or no project open."
        try:
            system.ui.error(msg)
        except NameError:
            print("Error:", msg)
        return entry.result(False, msg)

    # Create export directory
    if not os.path.exists(export_dir):
        os.makedirs(export_dir)
    
    # Ensure Git config files exist
    ensure_git_configs(export_dir)
    
    # Create project binary backup (moved down)
    
    unhandled.start()
    print("=== Starting Project Export ===")
    # The multipleApps flag is set after the main loop, from the classification
    # that loop already performs. Doing it up front meant a second recursive
    # walk reading a property off every object -- 13% of a cached export, for a
    # flag only Project_Build reads (and refreshes itself).
    start_time = time.time()
    reset_interaction_timer()
    print("Export directory: " + export_dir)
    
    # Flags and tracking
    from engine.codesys_utils import get_project_prop
    export_xml = get_project_prop(props.EXPORT_XML, False)
    backup_binary = get_project_prop(props.BACKUP_BINARY, False)
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
    skipped_count = 0
    app_count = 0
    
    # Metadata migration - no longer used
    
    # Property accessors collected dynamically during main loop
    property_accessors = {}
    
    # Initialize managers
    managers = create_import_managers()
    
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

    # Second pass: export all objects
    for obj in all_objects:
        try:
            obj_guid = safe_str(obj.guid)
            cached_type = cache_data.get('types', {}).get(obj_guid)
            cached_rel_path = cached_type[2] if (cached_type and len(cached_type) > 2) else None
            if cached_rel_path:
                # Fast path: trust the cache ONLY for objects that previously had
                # a real path (i.e. were exported). Never trust a cached "skip"
                # (rel_path None) -- the set of supported types can change between
                # versions, so always re-classify skipped objects. Otherwise a
                # once-skipped object stays buried forever even after its type
                # becomes exportable.
                effective_type, is_xml = cached_type[0], cached_type[1]
                should_skip = False
                # Validate the cached path against the live tree, exactly like
                # compare does. Without this, an object stays pinned to whatever
                # path an older version computed (e.g. the retired
                # '<Parent>/<Name>.<kind>.xml' layout) and export keeps writing
                # there forever while compare/import expect the current layout.
                fresh_path = build_expected_path(obj, effective_type, is_xml)
                if fresh_path and fresh_path != cached_rel_path:
                    # The path disagrees: the object moved/renamed in the IDE, or
                    # the cached classification predates the current profile.
                    # Re-classify instead of trusting either stale half.
                    log_info("Path invalidated for GUID %s: '%s' -> re-classifying"
                             % (obj_guid, cached_rel_path))
                    effective_type, is_xml, should_skip = classify_object(obj)
                    rel_path = build_expected_path(obj, effective_type, is_xml) if not should_skip else None
                else:
                    rel_path = cached_rel_path
            else:
                effective_type, is_xml, should_skip = classify_object(obj)
                rel_path = build_expected_path(obj, effective_type, is_xml) if not should_skip else None
            
            # Store for next cache save (always)
            context['new_types'][obj_guid] = (effective_type, is_xml, rel_path)

            # Free: the type is already resolved, so the multipleApps flag no
            # longer needs its own pass over the project.
            if effective_type == TYPE_GUIDS["application"]:
                app_count += 1
            
            if rel_path:
                norm_path = normalize_path(rel_path)
            else:
                norm_path = None
            
            # --- PROPERTY ACCESSOR COLLECTION ---
            if effective_type == TYPE_GUIDS["property"]:
                try:
                    if obj_guid not in context['property_accessors']:
                        context['property_accessors'][obj_guid] = {'get': None, 'set': None}
                    
                    for child in obj.get_children():
                        child_name = child.get_name().upper()
                        if child_name == "GET":
                            context['property_accessors'][obj_guid]['get'] = child
                        elif child_name == "SET":
                            context['property_accessors'][obj_guid]['set'] = child
                except Exception as e:
                    # Without its accessors the property still gets a file,
                    # but an empty GET/SET, so say whose (SPEC D13).
                    log_warning("Could not read the accessors of %s: %s"
                                % (unhandled.name_of(obj), safe_str(e)))
            
            # --- PERSIST CACHE FOR SKIPPED OBJECTS ---
            if cache_data and norm_path:
                try:
                    cached_obj = cache_data.get('objects', {}).get(norm_path)
                    if cached_obj:
                        new_cache[norm_path] = cached_obj
                except (AttributeError, TypeError):
                    pass  # A cache file of the wrong shape is no cache.
            # ----------------------------------------

            if should_skip:
                continue

            # Per-kind sync direction (profiles/default.json)
            if not kind_allows_export(effective_type):
                log_info("Skipping export of %s (sync_direction=%s)"
                         % (rel_path, sync_direction_of(effective_type)))
                continue

            # XML gate: skip non-always-exported XML types when export_xml is off
            if is_xml and effective_type in XML_TYPES:
                always_exported = effective_type in [
                    TYPE_GUIDS["task_config"], TYPE_GUIDS["nvl_sender"], TYPE_GUIDS["nvl_receiver"]
                ]
                if not always_exported and not export_xml:
                    continue

            # Select manager
            if is_xml:
                manager = managers["native"] if effective_type not in managers else managers[effective_type]
            elif effective_type in managers:
                manager = managers[effective_type]
            else:
                manager = managers["default"]

            context['effective_type'] = effective_type
            wrote = manager.export(obj, context, rel_path=rel_path)
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

    set_application_count_flag(app_count)

    # Orphan cleanup now uses exported_paths set directly
    removed_count = cleanup_orphaned_files(export_dir, exported_paths)
    if removed_count is None:
        return entry.result(False, "Export cancelled during orphan cleanup.")

    # Calculate folder hashes (Merkle Tree) and save the updated cache
    if new_cache:
        # build_folder_hashes expects a dict of {path: ide_hash}
        just_hashes = {path: record.get('ide_hash') for path, record in new_cache.items()}
        folder_hashes = build_folder_hashes(just_hashes)
        save_sync_cache(export_dir, new_cache, folder_hashes, context.get('new_types'))
        log_info("Saved updated sync cache with {} objects and {} folders.".format(
            len(new_cache), len(folder_hashes)))
            
    # Save and back up BEFORE stopping the clock and announcing completion.
    # This step saves the project and, when enabled, copies the whole .project
    # binary; running it after the timer meant the reported figure excluded
    # the part of the wait that came after the popup said "complete".
    finalize_sync_operation(export_dir, projects_obj, is_import=False)

    print("=== Export Complete ===")
    interaction_time = get_interaction_seconds()
    elapsed_time = time.time() - start_time - interaction_time
    elapsed_text = format_elapsed(elapsed_time, interaction_time)
    print("New: " + str(exported_new) + ", Updated: " + str(exported_updated) + ", Identical: " + str(exported_identical) + ", Removed: " + str(removed_count))
    print("Skipped: " + str(skipped_count) + " objects (no textual content)")
    print("Time elapsed: " + elapsed_text)
    print("Completed at: " + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))

    exported_total = exported_new + exported_updated + exported_identical
    summary = "Updated: " + str(exported_updated) + ", Created: " + str(exported_new) + ", Removed: " + str(removed_count) + ", Failed: " + str(exported_failed) + " (Identical: " + str(exported_identical) + ")"
    if pending_import:
        summary += ", Waiting to be imported: " + ", ".join(pending_import)
    log_info("Export complete! " + summary + " Time elapsed: " + elapsed_text)

    # Record sync version; metadata file is written in debug mode only
    from engine.codesys_utils import save_sync_metadata
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
    return entry.result(not missing and not pending_import,
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
    from engine.codesys_utils import get_project_prop
    if not get_project_prop(props.FOLDER):
        from engine.settings import choose_sync_folder
        _folder, setup_error = choose_sync_folder(globals())
        if setup_error:
            return entry.result(False, setup_error)

    base_dir, error = load_base_dir()
    if error:
        try:
            system.ui.warning(error)
        except NameError:
            print("Error:", error)
        return entry.result(False, error)

    init_logging(base_dir)
    return export_project(base_dir)


if __name__ == "__main__":
    main()