# -*- coding: utf-8 -*-
"""Which engine body is behind each command, and how to press it.

Two callers press the same buttons: the watcher inside an IDE somebody is
using, and the headless launcher inside an IDE nobody can see. They differ in
how they are told what to do and where they put the answer, not in what
running a command means — so that part lives here rather than in both.

The bodies are engine/entry_*.py, reached by path and by sys.modules name so
this file never imports the engine, which is the direction SPEC D12 forbids.
`config` is the exception: project properties are plumbing, not object-tree
work, so cds/ide/config.py answers it and the result is wrapped to look like
any other command's.
"""
from __future__ import print_function

import os
import sys

from cds.ide import config, messages, silent

# The install root, the directory that holds engine/ and cds/:
# cds/ide/entries.py -> ../../
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ENGINE_PACKAGE = "engine"

# Command -> the entry body it presses, and the function that is its button.
# These are the bodies in engine/, not the stubs the IDE menu scans.
SCRIPTS = {
    "export": ("entry_export.py", "main"),
    "import": ("entry_import.py", "main"),
    "compare": ("entry_compare.py", "main"),
    "build": ("entry_build.py", "main"),
}

# Every command a project has to be open for, in the order verify runs them.
COMMANDS = sorted(SCRIPTS) + ["config"]


def forget_engine():
    """Drop the engine modules so the next command re-reads them from disk.

    Each entry script used to do this at its own module level, and the
    reason it did is this one: a watcher lives as long as the IDE does,
    so without it, editing engine code means restarting the IDE to see
    the change. Naming the package rather than importing it keeps the
    dependency pointing the way SPEC D12 requires.
    """
    for name in [n for n in sys.modules.keys()
                 if n.split(".")[0] == ENGINE_PACKAGE]:
        del sys.modules[name]


def run(ide_globals, command, args):
    """Run one command and hand back what it did, as a silent.Outcome.

    The verdict is the body's return value (SPEC D11); its dialogs are just
    what a person would have read.
    """
    if command == "config":
        return silent.Outcome([], "", result=config.run(ide_globals, args))
    script, entry = SCRIPTS[command]
    forget_engine()
    return silent.run(ide_globals, os.path.join(REPO_ROOT, "engine", script),
                      entry, args)


def tail(ide_globals, command, outcome):
    """What the body printed, plus what the IDE has to say about it.

    entry_build.py only reports counts; the errors themselves — object and
    line — live in the IDE's message store, and a caller that cannot see the
    IDE has no other way to reach them.
    """
    if command != "build":
        return outcome.stdout_tail
    report = messages.build_report(ide_globals)
    if not report:
        return outcome.stdout_tail
    return "\n".join([outcome.stdout_tail, "--- build messages ---"] + report)


def wrong_application(command, args, outcome):
    """Did build compile the application the caller asked for?

    entry_build.py only offers the chooser when the project property
    cds-text-sync-multipleApps is already true, and it refreshes that flag
    *after* choosing. So the first build after a second application appears
    skips the chooser entirely, compiles the active one and reports success —
    with --app silently doing nothing. Check the name it reports instead.
    """
    wanted = (args or {}).get("app")
    if command != "build" or not wanted:
        return None
    for message in outcome.messages:
        if wanted in message["text"]:
            return None
    return ("build did not use --app %r; the project's multiple-application "
            "flag is probably not set yet, so it built the active application "
            "instead. Run build again, or export once to refresh the flag."
            % (wanted,))
