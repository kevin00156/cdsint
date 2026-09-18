# -*- coding: utf-8 -*-
"""What perf_probe measures: one table of functions, one of methods.

Moved out of perf_probe.py unchanged. That file is past the 400-line hard
limit, so it has to be split before the next thing goes in (PRINCIPLES 2),
and the tables are the seam: they are the part a maintainer edits when the
engine renames something, and the only part a test can check on its own.

A row here is a promise that the engine still has that name. When it does
not, the probe measures one fewer thing and the report says so by omission
-- which reads as a function that cost nothing. install_probes() refuses to
run on a stale table, and tests/test_perf_probe.py fails on one.
"""
from __future__ import print_function


def skip_bucket(result):
    return "SKIPPED (cache hit)" if result else "worked"


def export_bucket(result):
    return str(result)


# ── what to measure ──────────────────────────────────────────────────
# (name, label) pairs. Grouped so the report reads as an argument rather
# than an undifferentiated list.

FUNCTIONS = [
    # per-object IDE attribute reads
    ("read_ide_attrs", "IDE:read_ide_attrs"),
    ("write_ide_attrs", "IDE:write_ide_attrs"),
    # parent-chain walks
    ("build_expected_path", "path:build_expected_path"),
    ("get_container_prefix", "path:get_container_prefix"),
    ("get_object_path", "path:get_object_path"),
    ("get_parent_pou_name", "path:get_parent_pou_name"),
    # classification (is_nvl does a native export per GVL)
    ("classify_object", "classify:classify_object"),
    ("is_nvl", "classify:is_nvl"),
    ("is_graphical_pou", "classify:is_graphical_pou"),
    # textual content extraction
    ("export_object_content", "content:export_object_content"),
    ("export_interface_declaration", "content:export_interface_declaration"),
    ("get_quick_ide_hash", "content:get_quick_ide_hash"),
    ("format_st_content", "content:format_st_content"),
    ("calculate_hash", "content:calculate_hash"),
    # tree lookups (import side)
    ("find_child_transparent", "tree:find_child_transparent"),
    ("find_object_by_path", "tree:find_object_by_path"),
    ("ensure_folder_path", "tree:ensure_folder_path"),
    # compare engine
    ("get_ide_content", "compare:get_ide_content"),
    ("contents_are_equal", "compare:contents_are_equal"),
    ("read_file", "compare:read_file"),
    ("scan_new_disk_files", "compare:scan_new_disk_files"),
    ("find_all_changes", "compare:find_all_changes"),
    ("detect_moved_files", "compare:detect_moved_files"),
    # import engine -- these only fire in import mode, and their cost scales
    # with how many files actually changed rather than with project size
    ("perform_import_items", "import:perform_import_items"),
    ("update_existing_object", "import:update_existing_object"),
    ("create_new_object", "import:create_new_object"),
    ("update_object_code", "import:update_object_code"),
    ("batch_import_native_xmls_with_children", "import:batch_native_xmls"),
    ("merge_native_xmls", "import:merge_native_xmls"),
    ("save_pou_children", "import:save_pou_children"),
    ("restore_pou_children", "import:restore_pou_children"),
    ("build_device_remap", "import:build_device_remap"),
    ("order_st_files_parents_first", "import:order_st_files"),
    ("find_parent_pou", "import:find_parent_pou"),
    ("determine_object_type", "import:determine_object_type"),
    ("find_logged_in_applications", "import:find_logged_in_applications"),
    # disk + cache
    ("parse_st_file", "disk:parse_st_file"),
    ("load_sync_cache", "cache:load_sync_cache"),
    ("save_sync_cache", "cache:save_sync_cache"),
    ("build_folder_hashes", "cache:build_folder_hashes"),
    ("file_signature", "disk:file_signature"),
    # end-of-run bookkeeping, none of which used to be measured
    ("finalize_sync_operation", "final:finalize_sync_operation"),
    ("save_project", "final:save_project"),
    ("copy_project", "final:copy_project"),
    ("create_safety_backup", "final:create_safety_backup"),
    ("save_sync_metadata", "final:save_sync_metadata"),
    ("cleanup_orphaned_files", "final:cleanup_orphaned_files"),
    ("ensure_git_configs", "setup:ensure_git_configs"),
    # logging (unconditional print() to the CODESYS console)
    ("log_info", "log:log_info"),
    ("log_warning", "log:log_warning"),
]


# (module, class, method, label, bucket_of) -- the methods a table of plain
# function names cannot reach. _patch_method reads the class's own __dict__,
# so a class that only inherits the method does not belong here.
METHODS = [
    ("engine.managers_base", "ObjectManager", "_try_cache_skip",
     "mgr:_try_cache_skip", skip_bucket),
    ("engine.managers_base", "ObjectManager", "_update_cache_entry",
     "mgr:_update_cache_entry", None),
    ("engine.managers_pou", "POUManager", "export", "mgr:POUManager.export", export_bucket),
    ("engine.managers_pou", "PropertyManager", "export", "mgr:PropertyManager.export", export_bucket),
    ("engine.managers_native", "NativeManager", "export", "mgr:NativeManager.export", export_bucket),
    ("engine.managers_native", "ConfigManager", "export", "mgr:ConfigManager.export", export_bucket),
    ("engine.managers_base", "FolderManager", "export", "mgr:FolderManager.export", None),
    ("engine.managers_native", "NativeManager", "_hash_file", "mgr:_hash_file", None),
    ("engine.managers_native", "NativeManager", "_hash_content", "mgr:_hash_content", None),
    # import side
    ("engine.managers_pou", "POUManager", "update", "mgr:POUManager.update", None),
    ("engine.managers_pou", "POUManager", "create", "mgr:POUManager.create", None),
    ("engine.managers_pou", "PropertyManager", "update", "mgr:PropertyManager.update", None),
    ("engine.managers_pou", "PropertyManager", "create", "mgr:PropertyManager.create", None),
    ("engine.managers_native", "NativeManager", "update", "mgr:NativeManager.update", None),
    ("engine.managers_native", "NativeManager", "create", "mgr:NativeManager.create", None),
    ("engine.managers_base", "FolderManager", "update", "mgr:FolderManager.update", None),
    ("engine.managers_base", "FolderManager", "create", "mgr:FolderManager.create", None),
]
