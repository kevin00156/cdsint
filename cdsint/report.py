# -*- coding: utf-8 -*-
"""Turning what came back into what a person, or an agent, reads.

One printer for both forms: a `--target` round trip and a `--project` launch
hand back the same result record (SPEC 4.3), and printing them differently
would make the two forms feel like two tools.

--json prints the record untouched. Everything else is a summary, and the
rule for the summary is that anything a caller would have to go and look up
elsewhere gets printed here instead.
"""
from __future__ import print_function

import json
import os
import re
import sys
import tempfile

# A property or a count that was never set. Printing the word None would read
# as a value.
UNSET = "(not set)"

# Report file names come from project names, and those have spaces, Chinese
# and punctuation in them.
_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def default_report(project):
    """Somewhere stable to put a run's report when the caller did not say.

    Named after the project so two projects verified side by side do not
    overwrite each other's answer, and kept rather than deleted because it is
    the only full record of what the IDE did.
    """
    stem = os.path.splitext(os.path.basename(project))[0]
    return os.path.join(tempfile.gettempdir(), "cdsint",
                        _SAFE.sub("_", stem) + ".json")


def as_json(record):
    print(json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False))


def warn_untrusted_exit(record):
    """Say when a headless run's exit code cannot be used as a gate.

    Whether an exit code survives the trip out of a GUI-subsystem exe is a
    fact to measure, not to assume (SPEC 6.4): the IDE-side script writes
    down the code it meant to use and the launcher compares. When they
    disagree, a caller reading only `$?` would draw the wrong conclusion, so
    it is told where the answer actually is.
    """
    if record.get("exit_code_trusted") or record.get("intended_exit") is None:
        return
    print("warning: %s meant to exit %s and the shell saw %s, so the exit "
          "code cannot be used as a gate here — read %s instead"
          % (record.get("install"), record["intended_exit"],
             record["exit_code_actual"], record.get("report_path")),
          file=sys.stderr)


def show_sync_dir(path, want_json=False):
    """Say which folder the run treats as the truth, before it uses it.

    A --json caller reads it from the record and the report file instead: a
    line of prose in front of the JSON would break the parse it was meant to
    inform.
    """
    if path and not want_json:
        print("sync folder: %s" % path)


def show(result, want_json=False):
    """Print one command's result record."""
    if want_json:
        return as_json(result)
    said = []
    for message in result.get("messages") or []:
        said.append(message.get("text", ""))
        print("%s: %s" % (message.get("level", "info"), said[-1]))
    _show_data(result.get("data") or {})
    _show_needs(result, said)
    # The error repeats the first bad message, or the question. Say it once.
    if result.get("error") and result["error"] not in said:
        print("error: " + result["error"], file=sys.stderr)
    if _wants_tail(result) and result.get("stdout_tail"):
        print("--- output from the IDE ---", file=sys.stderr)
        print(result["stdout_tail"], file=sys.stderr)


def show_steps(results, want_json=False):
    """Print several commands' results, saying which one each belongs to."""
    if want_json:
        return as_json(results)
    for result in results:
        print("--- %s (%.1fs) ---" % (result.get("command"),
                                      result.get("elapsed_s") or 0.0))
        show(result)


def show_installs(found, want_json=False):
    """Print what `cdsint installs` found."""
    if want_json:
        return as_json(found)
    if not found:
        print("no CODESYS, Lenze PLC Designer or Delta DIADesigner-AX install "
              "found under Program Files")
        return
    for install in found:
        print(install["name"])
        print("  exe        %s" % install["exe"])
        for profile in install["profiles"] or ["(none found — pass --profile)"]:
            print("  profile    %s" % profile)
        note = ("  (needs an elevated shell)"
                if install["script_dir_needs_admin"] else "")
        print("  ScriptDir  %s%s" % (install["script_dir"], note))
        if install["run_as_admin"]:
            # The launch failure this causes says only "requires elevation",
            # never who asked for it.
            print("  ADMIN      RUNASADMIN is set in %s, so starting this "
                  "from an ordinary shell will fail"
                  % install["run_as_admin"])


def _show_data(data):
    for key, value in sorted(data.items()):
        # A list or a mapping gets a line each. Those are the ones the reader
        # has to go and look up: the objects a command could not handle, the
        # type GUIDs discover did not recognise, its count per kind.
        if isinstance(value, dict):
            lines = ["%s %s" % (name, value[name]) for name in sorted(value)]
        elif isinstance(value, list):
            lines = [_one_line(item) for item in value]
        else:
            print("  %-16s %s" % (key, UNSET if value is None else value))
            continue
        print("  %-16s %d" % (key, len(lines)))
        for line in lines:
            print("  %-16s   %s" % ("", line))


def _one_line(item):
    """An unrecognised object is a name and a GUID; a failed one is a name."""
    if isinstance(item, dict):
        return "  ".join("%s" % item[name] for name in sorted(item))
    return item


def _show_needs(result, said):
    needs = result.get("needs_input")
    if not needs:
        return
    said.append(needs.get("question"))
    # Some dialogs have no flag that answers them — the sync-folder setup is
    # one. The question already says what to do instead, so naming a "--None"
    # flag would only be noise.
    arg = needs.get("arg")
    print("needs input: %s%s"
          % (said[-1], " (answer with --%s)" % arg if arg else ""),
          file=sys.stderr)


def _wants_tail(result):
    """When the summary is not the whole answer, show what the script printed.

    A failure always earns the room. So does compare, whose useful output is
    the per-object list it prints — the messages only carry the counts.
    """
    return not result.get("ok") or result.get("command") == "compare"
