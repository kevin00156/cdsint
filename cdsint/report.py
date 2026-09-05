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
import sys

# A property or a count that was never set. Printing the word None would read
# as a value.
UNSET = "(not set)"


def as_json(record):
    print(json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False))


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
        # A list gets a line each: the one that matters is the names of the
        # objects a command could not handle, and those are what the reader
        # has to go and look up.
        if isinstance(value, list):
            print("  %-16s %d" % (key, len(value)))
            for item in value:
                print("  %-16s   %s" % ("", item))
        else:
            print("  %-16s %s" % (key, UNSET if value is None else value))


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
