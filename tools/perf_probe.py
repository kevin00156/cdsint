# -*- coding: utf-8 -*-
"""perf_probe.py - Instrument the REAL sync engine and rank its costs.

A maintainer's instrument, not one of the tool's features, so it carries no
`Project_` prefix: that prefix means "an entry in the Scripts menu somebody
clicks", and only the three stubs in stub/ are that (PRINCIPLES 12).

It wraps the actual engine functions in place and then runs the real export
or compare, so whatever the engine does, the numbers below describe. The
predecessor it replaced re-implemented Pass 1 and had drifted away from what
the engine was really doing; it did not come across in the move to cdsint.

Every wrapped call records inclusive and exclusive time. Rank by EXCL to find
where time is really spent; read CALLS to spot per-object IDE round-trips.

How to run it. It is not a cdsint command and has no --target or --project
form; it profiles an IDE somebody already has open, with the project open in
it. In that IDE: Tools > Scripting > Execute Script File, and pick
tools/perf_probe.py. The mode is the one argument, taken from the script
arguments box (anything unrecognised leaves the default):

    (no argument)   profile a full export -- the default
    compare         profile the comparison only
    import          profile a full import

The report is printed and written to perf_probe_<mode>.txt in the sync
folder.

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
from __future__ import print_function

import os
import sys

# The same three lines in every tool here: make sure this directory is
# somewhere the import system will look, then let tools/_root.py put the
# install root there. Run from a shell, `python tools/x.py` already puts this
# directory on sys.path and the check does nothing; run inside the IDE it is
# the only thing that does, because ScriptEngine hands IronPython the file and
# sys.path is the IDE's own search list. Checked rather than inserted flat, so
# one tool importing another does not stack a second copy of the same entry.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import _root  # noqa: E402,F401
from perf_patch import _timer, install_probes  # noqa: E402
from perf_report import build_report  # noqa: E402


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
    strings, sync_log = [__import__("engine." + n, {}, {}, [n]) for n in ("strings", "sync_log")]
    engine = __import__("engine.change_detect", {}, {}, ["change_detect"])
    api = __import__("engine.entry", {}, {}, ["entry"])

    projects_obj = api.borrowed(globals(), "projects")
    if projects_obj is None or not projects_obj.primary:
        print("Error: no project open.")
        return

    settings = __import__("engine.settings", {}, {}, ["settings"])
    values, base_dir, error = settings.prepare(globals())
    if error is None and base_dir is None:
        error = settings.folder_missing(globals())
    if error:
        print("Error: " + strings.safe_str(error))
        return
    sync_log.init_logging(base_dir, values["debug"])

    functions, sites = install_probes()
    if not functions:
        print("Stopping: with no probes there is nothing to measure.")
        return
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
        results = engine.find_all_changes(base_dir, projects_obj,
                                          export_xml=values["export_xml"])
        print("")
        print("different=%d  new_in_ide=%d  new_on_disk=%d  unchanged=%d"
              % (len(results["different"]), len(results["new_in_ide"]),
                 len(results["new_on_disk"]), results["unchanged_count"]))
    elif mode == "import":
        entry.import_project(base_dir, values, projects_obj)
    else:
        entry.export_project(base_dir, values, projects_obj)
    wall = _timer() - start

    # The operation resets this at its own start, so what is left is the dialog
    # time for this run. Import always confirms before touching the IDE, and
    # counting a human's deliberation as sync time would swamp everything else.
    try:
        interaction = sync_log.get_interaction_seconds()
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
        print("Could not write report: " + strings.safe_str(exc))


if __name__ == "__main__":
    main()
