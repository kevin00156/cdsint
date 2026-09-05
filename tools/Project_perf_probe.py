# -*- coding: utf-8 -*-
"""Project_perf_probe.py - Instrument the REAL sync engine and rank its costs.

It wraps the actual engine functions in place and then runs the real export
or compare, so whatever the engine does, the numbers below describe. The
predecessor it replaced re-implemented Pass 1 and had drifted away from what
the engine was really doing; it did not come across in the move to cdsint.

Every wrapped call records inclusive and exclusive time. Rank by EXCL to find
where time is really spent; read CALLS to spot per-object IDE round-trips.

Usage inside CODESYS (Scripting > Execute Script File):
    Project_perf_probe.py              -> profile a full export
    Project_perf_probe.py compare      -> profile the comparison only
    Project_perf_probe.py import       -> profile a full import

Notes:
  * export and import modes run the REAL operation. Import CREATES, UPDATES,
    MOVES and DELETES objects in the open project, exactly as the import
    entry would; take a backup first and expect the usual confirmation dialog.
  * compare mode touches nothing in the IDE, but it does rewrite
    sync_cache.json.
  * An import is two phases with very different costs: find_all_changes
    (read-only, scales with project size) and perform_import_items (scales
    with how many files actually changed). compare mode profiles the first
    phase on its own, which is nearly all of an import that has nothing to do.
  * Time spent waiting on dialogs is measured separately and excluded from the
    wall clock, so the figure reflects the sync rather than the operator.
  * Run the same mode TWICE in a row. The second run is the one that shows
    whether the cache is doing its job.
"""
import os
import sys
import time

# tools/ sits beside engine/, and the IDE runs this file by absolute path, so
# nothing else puts the install root on sys.path for us.
_INSTALL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _INSTALL_ROOT not in sys.path:
    sys.path.insert(0, _INSTALL_ROOT)

from cds.core import props  # noqa: E402

# High-resolution timer. On Python 2 / Windows time.clock() is
# QueryPerformanceCounter; time.time() only has ~15 ms granularity there, which
# is far too coarse for per-object calls.
try:
    _timer = time.clock
except AttributeError:
    _timer = time.time


# ═══════════════════════════════════════════════════════════════════
#  INSTRUMENTATION
# ═══════════════════════════════════════════════════════════════════

_stats = {}          # label -> {"calls", "incl", "excl"}
_tallies = {}        # label -> {bucket: count}
_stack = []          # accumulated child time of each active frame


def _record(label, elapsed, child):
    s = _stats.get(label)
    if s is None:
        s = _stats[label] = {"calls": 0, "incl": 0.0, "excl": 0.0}
    s["calls"] += 1
    s["incl"] += elapsed
    s["excl"] += (elapsed - child)


def _tally(label, bucket):
    t = _tallies.get(label)
    if t is None:
        t = _tallies[label] = {}
    t[bucket] = t.get(bucket, 0) + 1


def _make_wrapper(label, func, bucket_of=None):
    def wrapper(*args, **kwargs):
        _stack.append(0.0)
        start = _timer()
        try:
            result = func(*args, **kwargs)
            if bucket_of is not None:
                try:
                    _tally(label, bucket_of(result))
                except Exception:
                    pass
            return result
        finally:
            elapsed = _timer() - start
            child = _stack.pop()
            if _stack:
                _stack[-1] = _stack[-1] + elapsed
            _record(label, elapsed, child)
    return wrapper


def _patch_function(name, label=None, bucket_of=None):
    """Rebind a module-level function in EVERY namespace that imported it.

    `from codesys_utils import read_ide_attrs` copies the function object into
    the importing module, so patching only the defining module would miss most
    call sites. Identity comparison finds them all.
    """
    label = label or name
    original = None
    for module in list(sys.modules.values()):
        if module is None:
            continue
        try:
            candidate = getattr(module, name, None)
        except Exception:
            continue
        # Anything under engine/, which is both the codesys_* modules and the
        # entry bodies: cleanup_orphaned_files lives in entry_export.
        owner = getattr(candidate, "__module__", None) if candidate is not None else None
        if owner and owner.startswith("engine."):
            original = candidate
            break
    if original is None:
        return 0

    wrapper = _make_wrapper(label, original, bucket_of)
    patched = 0
    for module in list(sys.modules.values()):
        if module is None:
            continue
        try:
            if getattr(module, name, None) is original:
                setattr(module, name, wrapper)
                patched += 1
        except Exception:
            continue
    return patched


def _patch_method(module_name, class_name, method_name, label=None, bucket_of=None):
    """Wrap a method on a class. Subclasses that do not override it inherit
    the wrapper automatically."""
    label = label or ("%s.%s" % (class_name, method_name))
    module = sys.modules.get(module_name)
    if module is None:
        return 0
    cls = getattr(module, class_name, None)
    if cls is None:
        return 0
    original = cls.__dict__.get(method_name)
    if original is None:
        return 0
    setattr(cls, method_name, _make_wrapper(label, original, bucket_of))
    return 1


# ── what to measure ──────────────────────────────────────────────────
# (name, label) pairs. Grouped so the report reads as an argument rather
# than an undifferentiated list.

_FUNCTIONS = [
    # project-property round trips (each one is a get_project_info() call)
    ("get_project_prop", "IDE:get_project_prop"),
    ("is_debug", "IDE:is_debug"),
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
    ("_find_child_transparent", "tree:_find_child_transparent"),
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
    ("check_version_compatibility", "import:check_version_compatibility"),
    # disk + cache
    ("parse_st_file", "disk:parse_st_file"),
    ("load_sync_cache", "cache:load_sync_cache"),
    ("save_sync_cache", "cache:save_sync_cache"),
    ("build_folder_hashes", "cache:build_folder_hashes"),
    ("file_signature", "disk:file_signature"),
    # end-of-run bookkeeping -- project.save() and a full .project copy live
    # in here, and none of it used to be measured
    ("finalize_sync_operation", "final:finalize_sync_operation"),
    ("backup_project_binary", "final:backup_project_binary"),
    ("create_safety_backup", "final:create_safety_backup"),
    ("save_sync_metadata", "final:save_sync_metadata"),
    ("cleanup_orphaned_files", "final:cleanup_orphaned_files"),
    ("ensure_git_configs", "setup:ensure_git_configs"),
    ("update_application_count_flag", "setup:update_application_count_flag"),
    ("load_base_dir", "setup:load_base_dir"),
    ("resolve_projects", "setup:resolve_projects"),
    # logging (unconditional print() to the CODESYS console)
    ("log_info", "log:log_info"),
    ("log_warning", "log:log_warning"),
]


def _skip_bucket(result):
    return "SKIPPED (cache hit)" if result else "worked"


def _export_bucket(result):
    return str(result)


def install_probes():
    """Wrap everything. Returns (functions_patched, sites_rebound)."""
    functions = 0
    sites = 0
    for entry in _FUNCTIONS:
        name, label = entry
        n = _patch_function(name, label)
        if n:
            functions += 1
            sites += n

    methods = [
        ("engine.codesys_managers", "ObjectManager", "_try_cache_skip",
         "mgr:_try_cache_skip", _skip_bucket),
        ("engine.codesys_managers", "ObjectManager", "_update_cache_entry",
         "mgr:_update_cache_entry", None),
        ("engine.codesys_managers", "POUManager", "export", "mgr:POUManager.export", _export_bucket),
        ("engine.codesys_managers", "PropertyManager", "export", "mgr:PropertyManager.export", _export_bucket),
        ("engine.codesys_managers", "NativeManager", "export", "mgr:NativeManager.export", _export_bucket),
        ("engine.codesys_managers", "ConfigManager", "export", "mgr:ConfigManager.export", _export_bucket),
        ("engine.codesys_managers", "FolderManager", "export", "mgr:FolderManager.export", None),
        ("engine.codesys_managers", "NativeManager", "_hash_file", "mgr:_hash_file", None),
        ("engine.codesys_managers", "NativeManager", "_hash_content", "mgr:_hash_content", None),
        # import side
        ("engine.codesys_managers", "POUManager", "update", "mgr:POUManager.update", None),
        ("engine.codesys_managers", "POUManager", "create", "mgr:POUManager.create", None),
        ("engine.codesys_managers", "PropertyManager", "update", "mgr:PropertyManager.update", None),
        ("engine.codesys_managers", "PropertyManager", "create", "mgr:PropertyManager.create", None),
        ("engine.codesys_managers", "NativeManager", "update", "mgr:NativeManager.update", None),
        ("engine.codesys_managers", "NativeManager", "create", "mgr:NativeManager.create", None),
        ("engine.codesys_managers", "ConfigManager", "update", "mgr:ConfigManager.update", None),
        ("engine.codesys_managers", "ConfigManager", "create", "mgr:ConfigManager.create", None),
        ("engine.codesys_managers", "FolderManager", "update", "mgr:FolderManager.update", None),
        ("engine.codesys_managers", "FolderManager", "create", "mgr:FolderManager.create", None),
    ]
    for module_name, class_name, method_name, label, bucket in methods:
        n = _patch_method(module_name, class_name, method_name, label, bucket)
        if n:
            functions += 1
            sites += n

    return functions, sites


# ═══════════════════════════════════════════════════════════════════
#  REPORT
# ═══════════════════════════════════════════════════════════════════

def build_report(mode, wall_seconds, object_count, functions, sites,
                 tree_seconds=0.0, interaction_seconds=0.0):
    lines = []
    add = lines.append

    add("=" * 78)
    add("PERF PROBE  --  mode=%s" % mode)
    add("=" * 78)
    add("wall clock      : %.2f s%s"
        % (wall_seconds,
           ("   (excludes %.2f s waiting on dialogs)" % interaction_seconds)
           if interaction_seconds >= 0.05 else ""))
    add("IDE objects     : %s" % (object_count if object_count is not None else "n/a"))
    add("probes active   : %d functions across %d bound names" % (functions, sites))
    add("timer           : %s" % getattr(_timer, "__name__", "?"))
    add("")
    add("EXCL = time inside the function itself (nested probes subtracted).")
    add("INCL = wall time including everything it called.")
    add("Rank by EXCL for cost; read CALLS for per-object IDE round-trips.")
    add("")

    rows = []
    for label in _stats:
        s = _stats[label]
        rows.append((s["excl"], s["incl"], s["calls"], label))
    rows.sort(reverse=True)

    add("-" * 78)
    add("%-34s %8s %10s %10s %9s" % ("FUNCTION", "CALLS", "EXCL(s)", "INCL(s)", "us/call"))
    add("-" * 78)
    for excl, incl, calls, label in rows:
        per_call = (incl / calls * 1000000.0) if calls else 0.0
        add("%-34s %8d %10.3f %10.3f %9.1f" % (label, calls, excl, incl, per_call))

    total_excl = sum(r[0] for r in rows)
    add("-" * 78)
    add("%-34s %8s %10.3f" % ("total measured (excl)", "", total_excl))
    if wall_seconds > 0:
        add("%-34s %8s %10.3f  (%.0f%% of wall clock)"
            % ("unmeasured", "", max(0.0, wall_seconds - total_excl),
               100.0 * max(0.0, wall_seconds - total_excl) / wall_seconds))
    if tree_seconds:
        add("")
        add("get_children(recursive=True) sampled separately: %.3f s" % tree_seconds)
        add("  A method on the project object, so it cannot be wrapped. The")
        add("  engine makes this same call inside the measured region, so")
        add("  expect roughly this much of 'unmeasured' to be it.")

    if _tallies:
        add("")
        add("-" * 78)
        add("RETURN-VALUE TALLIES")
        add("-" * 78)
        for label in sorted(_tallies):
            buckets = _tallies[label]
            total = sum(buckets.values())
            add("  %s  (%d calls)" % (label, total))
            pairs = sorted(buckets.items(), key=lambda kv: -kv[1])
            for bucket, count in pairs:
                share = (100.0 * count / total) if total else 0.0
                add("      %-26s %6d  %5.1f%%" % (bucket, count, share))

    # ── the two numbers that decide the whole diagnosis ──
    add("")
    add("=" * 78)
    add("KEY RATIOS")
    add("=" * 78)

    # An import is two phases with unrelated cost drivers. Which one dominates
    # decides whether to look at the comparison or at the applying of changes.
    compare_phase = _stats.get("compare:find_all_changes")
    apply_phase = _stats.get("import:perform_import_items")
    if compare_phase or apply_phase:
        if compare_phase:
            add("phase 1 find_all_changes : %6.2f s  -- read-only, scales with "
                "project size" % compare_phase["incl"])
        if apply_phase:
            add("phase 2 perform_import   : %6.2f s  -- scales with how many "
                "files changed" % apply_phase["incl"])
        add("")

    skip = _tallies.get("mgr:_try_cache_skip", {})
    if skip:
        hits = skip.get("SKIPPED (cache hit)", 0)
        total = sum(skip.values())
        add("cache skip rate        : %d/%d  (%.1f%%)"
            % (hits, total, 100.0 * hits / total if total else 0.0))
        add("   On an unchanged second run this should be near 100%.")
        add("   Near 0%% means the cache is being rejected, not that work is needed.")

    objs = object_count or 0
    for label, note in [
        ("IDE:is_debug", "get_project_info() round trips just to read a debug flag"),
        ("IDE:read_ide_attrs", "per-object build_properties reads"),
        ("path:get_container_prefix", "parent-chain walks to the project root"),
        ("content:export_object_content", "textual decl/impl extractions"),
        ("tree:_find_child_transparent", "sibling scans during tree lookup"),
    ]:
        s = _stats.get(label)
        if s and objs:
            add("%-22s : %d calls = %.2f per object  -- %s"
                % (label.split(":")[-1], s["calls"], float(s["calls"]) / objs, note))

    add("")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
#  DRIVER
# ═══════════════════════════════════════════════════════════════════

# The probes go in after the entry body is imported: importing it is what
# pulls in the codesys_* modules the probes rebind.
_ENTRY_FOR_MODE = {
    "export": "entry_export",
    "compare": "entry_export",   # find_all_changes comes along with it
    "import": "entry_import",
}


def main():
    mode = "export"
    for arg in sys.argv[1:]:
        low = str(arg).strip().lower()
        if low in _ENTRY_FOR_MODE:
            mode = low

    entry_name = _ENTRY_FOR_MODE[mode]
    # __import__ with a fromlist hands back the submodule itself, and it
    # means the same thing in IronPython 2.7 and CPython 3.
    entry = __import__("engine." + entry_name, {}, {}, [entry_name])

    utils = sys.modules.get("engine.codesys_utils")
    engine = sys.modules.get("engine.codesys_compare_engine")
    if utils is None or engine is None:
        print("Could not load the engine modules.")
        return

    projects_obj = utils.resolve_projects(None, globals())
    if projects_obj is None or not projects_obj.primary:
        print("Error: no project open.")
        return

    base_dir, error = utils.load_base_dir()
    if error:
        print("Error: " + utils.safe_str(error))
        return
    utils.init_logging(base_dir)

    functions, sites = install_probes()
    print("Perf probe armed: %d functions, %d bound names. Mode=%s" % (functions, sites, mode))
    print("Base dir: " + base_dir)
    print("")

    # Time the recursive tree fetch separately. It is a method on the CODESYS
    # project object, so it cannot be wrapped like a module function, and the
    # engine makes the same call itself inside the measured region.
    object_count = None
    tree_seconds = 0.0
    try:
        tree_start = _timer()
        object_count = len(projects_obj.primary.get_children(recursive=True))
        tree_seconds = _timer() - tree_start
    except Exception:
        pass

    if mode == "import":
        print("*** import mode performs a REAL import: objects will be")
        print("*** created, updated, moved and deleted in the open project.")
        print("")

    start = _timer()
    if mode == "compare":
        export_xml = utils.get_project_prop(props.EXPORT_XML, False)
        results = engine.find_all_changes(base_dir, projects_obj, export_xml=export_xml)
        print("")
        print("different=%d  new_in_ide=%d  new_on_disk=%d  unchanged=%d"
              % (len(results["different"]), len(results["new_in_ide"]),
                 len(results["new_on_disk"]), results["unchanged_count"]))
    elif mode == "import":
        entry.import_project(projects_obj)
    else:
        entry.export_project(base_dir, projects_obj)
    wall = _timer() - start

    # The operation resets this at its own start, so what is left is the dialog
    # time for this run. Import always confirms before touching the IDE, and
    # counting a human's deliberation as sync time would swamp everything else.
    try:
        interaction = utils.get_interaction_seconds()
    except Exception:
        interaction = 0.0
    wall = max(0.0, wall - interaction)

    report = build_report(mode, wall, object_count, functions, sites, tree_seconds,
                          interaction)
    print("")
    print(report)

    out_path = os.path.join(base_dir, "perf_probe_%s.txt" % mode)
    try:
        import codecs
        with codecs.open(out_path, "w", "utf-8") as handle:
            handle.write(report)
        print("Report written to: " + out_path)
    except Exception as exc:
        print("Could not write report: " + utils.safe_str(exc))


if __name__ == "__main__":
    main()
