# -*- coding: utf-8 -*-
"""Can this IDE's IronPython import every module cdsint installs?

The engine used to be .pyw files at the repo root loaded through
imp.load_source, so package imports were never exercised inside an IDE. They
are now the only way the code loads, and the three IDE families ship three
different IronPython builds (2.7.7, 2.7.12). This answers, per IDE, whether
that works at all — before anything harder is attempted.

Run it headless, and read the file rather than the console:

    <exe> --profile="<name>" --noUI --runscript="<abs path to this file>"

The report goes to %TEMP%\\cdsint-work\\probe_imports-<pid>.txt, or to
CDS_PROBE_OUT if that is set. A GUI-subsystem exe hands a shell no output, so
writing the file is the only reliable channel; the last line is OK or FAILED.
"""
from __future__ import print_function

import os
import sys
import traceback

_INSTALL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _INSTALL_ROOT not in sys.path:
    sys.path.insert(0, _INSTALL_ROOT)

# Every module that has to load inside the IDE. codesys_ui and codesys_ui_diff
# import clr and WinForms at module level, so they are part of the question,
# not an extra.
MODULES = [
    "engine",
    "engine.entry",
    "engine.codesys_constants",
    "engine.codesys_utils",
    "engine.codesys_managers",
    "engine.codesys_compare_engine",
    "engine.codesys_ui",
    "engine.codesys_ui_diff",
    "engine.codesys_online",
    "engine.entry_export",
    "engine.entry_import",
    "engine.entry_compare",
    "engine.entry_build",
    "engine.entry_plc",
    "engine.settings",
    "engine.unhandled",
    "cds",
    "cds.core",
    "cds.core.ipc",
    "cds.core.instances",
    "cds.core.commands",
    "cds.ide",
    "cds.ide.session",
    "cds.ide.watcher",
    "cds.ide.silent",
    "cds.ide.entries",
    "cds.ide.config",
    "cds.ide.permit",
    "cds.ide.headless",
    "cds.ide.project",
    "cds.ide.display",
    "cds.ide.messages",
]


def report_path():
    override = os.environ.get("CDS_PROBE_OUT")
    if override:
        return override
    base = os.path.join(os.environ.get("TEMP", "."), "cdsint-work")
    if not os.path.exists(base):
        os.makedirs(base)
    return os.path.join(base, "probe_imports-%s.txt" % os.getpid())


def try_import(name):
    """Import one module. Returns None, or the traceback that stopped it."""
    try:
        __import__(name)
        return None
    except Exception:
        return traceback.format_exc()


def run():
    lines = ["install root: " + _INSTALL_ROOT,
             "python: " + sys.version.replace("\n", " "),
             "executable: " + str(sys.executable),
             ""]
    failed = []
    for name in MODULES:
        problem = try_import(name)
        lines.append(("  ok   " if problem is None else "  FAIL ") + name)
        if problem is not None:
            failed.append((name, problem))

    lines.append("")
    # The profile is loaded from profiles/ next to engine/, which is the one
    # path that had to change when the engine moved into a package.
    lines.append(_profile_check())
    lines.append("")
    for name, problem in failed:
        lines.append("--- " + name + " ---")
        lines.append(problem)
    lines.append("FAILED %d of %d" % (len(failed), len(MODULES))
                 if failed else "OK")
    return "\n".join(lines)


def _profile_check():
    try:
        from engine.codesys_constants import TYPE_GUIDS, SCRIPT_VERSION
        return ("profile: %d type guids loaded, version %s"
                % (len(TYPE_GUIDS), SCRIPT_VERSION))
    except Exception:
        return "profile: FAILED\n" + traceback.format_exc()


def main():
    text = run()
    path = report_path()
    handle = open(path, "wb")
    try:
        handle.write(text.encode("utf-8"))
    finally:
        handle.close()
    print(text)
    print("report: " + path)


main()
