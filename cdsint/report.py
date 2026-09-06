# -*- coding: utf-8 -*-
"""Turning what came back into what a person, or an agent, reads.

Everything cdsint prints is printed here. One printer for both forms: a
`--target` round trip and a `--project` launch hand back the same result
record (SPEC 4.3), and printing them differently would make the two forms
feel like two tools. The runners used to print as well — a lock warning here,
a kill warning there, the `list` table somewhere else — and the cost was that
`--json` could not be honoured in one place, so a caller reading JSON got
prose on stderr it had no way to attach to anything.

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


def untrusted_exit(record):
    """Say when a headless run's exit code cannot be used as a gate, or None.

    Whether an exit code survives the trip out of a GUI-subsystem exe is a
    fact to measure, not to assume (SPEC 6.4): the IDE-side script writes
    down the code it meant to use and the launcher compares. When they
    disagree, a caller reading only `$?` would draw the wrong conclusion, so
    it is told where the answer actually is.
    """
    if record.get("exit_code_trusted") or record.get("intended_exit") is None:
        return None
    return ("%s meant to exit %s and the shell saw %s, so the exit code "
            "cannot be used as a gate here — read %s instead"
            % (record.get("install"), record["intended_exit"],
               record["exit_code_actual"], record.get("report_path")))


def show_sync_dir(path, want_json=False):
    """Say which folder the run treated as the truth (SPEC 4.2).

    Printed after the run rather than before it, because until the IDE has
    read the project's settings file nobody out here knows the answer:
    --sync-dir is an override that may not have been given. Nothing else of
    ours reaches stdout first, so this is still the first line.

    A --json caller reads it from the record and the report file instead: a
    line of prose in front of the JSON would break the parse it was meant to
    inform.
    """
    if path and not want_json:
        print("sync folder: %s" % path)


def show(result, want_json=False):
    """Print one command's result record.

    Indexed, not .get()-ed. Every producer builds these through
    cds/core/commands.py new_result, so all twelve fields are there; the
    defensive version could not tell a field that is legitimately null from
    one a producer forgot, which is how the refusal record went seven fields
    short for a year without anything noticing. `notes` is the exception and
    the reason is below.
    """
    if want_json:
        return as_json(result)
    _show_notes(result)
    said = [message["text"] for message in result["messages"]]
    for message in result["messages"]:
        print("%s: %s" % (message["level"], message["text"]))
    _show_data(result["data"] or {})
    question = _show_needs(result)
    # A needs_input record IS the error: cds/ide/outcome.py error_text()
    # returns the question when a dialog went unanswered. That one is
    # structural, so it is answered structurally. What is left is a body that
    # says the same sentence twice -- system.ui.error(msg) and then
    # result(False, msg) -- and that is a producer in engine/, not something
    # this can fix by comparing prose. It is compared here anyway, once, so
    # the reader does not see it twice while ENGINE_PLAN.md gets to it.
    if result["error"] and result["error"] != question \
            and result["error"] not in said:
        print("error: " + result["error"], file=sys.stderr)
    if not result["ok"] and result["stdout_tail"]:
        print("--- output from the IDE ---", file=sys.stderr)
        print(result["stdout_tail"], file=sys.stderr)


def show_steps(results, want_json=False):
    """Print several commands' results, saying which one each belongs to."""
    if want_json:
        return as_json(results)
    for result in results:
        print("--- %s (%.1fs) ---" % (result["command"], result["elapsed_s"]))
        show(result)


def show_verify(problems, describe):
    """The verdict over a whole round trip, which no single step carries.

    compare can pass every step and still have found differences, so this is
    not a restatement of the records above it (cdsint/verify.py problems).
    Said in both modes for that reason: a --json caller could work it out
    from the records, but only by re-implementing what verify decided.
    """
    for problem in problems:
        print("verify: " + problem, file=sys.stderr)
    if not problems:
        print("verify: %s round-tripped and built cleanly" % describe)


def show_instances(regs, want_json=False):
    """Print what `cdsint list` found: who is listening, and on what."""
    if want_json:
        return as_json(regs)
    if not regs:
        # An empty list is the answer to "who is listening", not a failure,
        # so the caller still gets exit 0 (SPEC 4.3).
        print("no IDE is listening; start Project_watch.py in one")
        return
    for reg in regs:
        print("%-28s %-6s %s" % (reg["instance_id"], reg.get("state", "?"),
                                 reg.get("project_path") or "(no project)"))


def show_installs(found, want_json=False):
    """Print what `cdsint installs` found."""
    if want_json:
        return as_json(found)
    if not found:
        print("no CODESYS-family IDE found on this machine")
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


def _show_notes(result):
    """What the launcher had to say about the run, as opposed to about the work.

    A lock it removed, an IDE it had to kill, an exit code it cannot vouch
    for. The --target form has none of this, so the field is only on the
    records the --project form hands back, next to `ide` and `report_path` —
    which is why this is the one .get() in here.
    """
    for note in result.get("notes") or []:
        print("warning: " + note, file=sys.stderr)


def _show_data(data):
    for key, value in sorted(data.items()):
        # A list or a mapping gets a line each. Those are the ones the reader
        # has to go and look up: the objects a command could not handle, the
        # type GUIDs discover did not recognise, the objects compare found a
        # difference in.
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


def _show_needs(result):
    """Print the question nobody could answer, and hand it back.

    Handed back rather than appended to a list the caller owns: show() needs
    to know it printed the question so it does not print the same sentence
    again as the error, and reaching into the caller's variable to say so was
    two functions sharing one thought.
    """
    needs = result["needs_input"]
    if not needs:
        return None
    # Some dialogs have no flag that answers them — the sync-folder setup is
    # one. The question already says what to do instead, so naming a "--None"
    # flag would only be noise.
    print("needs input: %s%s"
          % (needs["question"], " (answer with --%s)" % needs["arg"]
             if needs["arg"] else ""),
          file=sys.stderr)
    return needs["question"]
