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

The plc commands are the other odd pair. They reach the same engine bodies
the same way, but only one of the two callers may press them and only when
the project says so, so both gates — cds/ide/permit.py and WATCHER_REFUSES
below — sit here, in front of the press.
"""
from __future__ import print_function

import os
import sys

from cds.core import props
from cds.ide import config, messages, permit, silent

# The install root, the directory that holds engine/ and cds/:
# cds/ide/entries.py -> ../../
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ENGINE_PACKAGE = "engine"

# Command -> the entry body it presses, and the function that is its button.
# These are the bodies in engine/, not the stubs the IDE menu scans. The two
# plc commands share a file and differ by which function is pressed, so the
# action needs no dispatcher of its own.
SCRIPTS = {
    "export": ("entry_export.py", "main"),
    "import": ("entry_import.py", "main"),
    "compare": ("entry_compare.py", "main"),
    "discover": ("entry_discover.py", "main"),
    "build": ("entry_build.py", "main"),
    "plc connect": ("entry_plc.py", "connect"),
    "plc download": ("entry_plc.py", "download"),
}

# What the watcher will not run, whoever asks. Logging into a PLC takes the
# online session away from the person sitting in front of that IDE, so the
# watcher has no business doing it (SPEC D8). The CLI stops a `plc --target`
# at the parser; this is the same rule where a hand-written command file
# would otherwise land, and it answers by name rather than by pretending the
# command does not exist.
WATCHER_REFUSES = dict(
    (name, "%s only runs in the --project form. The watcher lives inside an "
           "IDE somebody is using, and logging into a PLC would take their "
           "online session away from them (SPEC D8)." % name)
    for name in SCRIPTS if name.startswith("plc "))

# Every command the watcher answers by pressing an engine body.
COMMANDS = sorted(set(SCRIPTS) - set(WATCHER_REFUSES)) + ["config"]

# What the two layers of the PLC gate are called on the wire, so the pieces
# either side of it — the CLI's subcommand, this table, cds/ide/permit.py —
# do not each spell the split their own way.
PLC_PREFIX = "plc "


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
        answer = silent.Outcome([], "", result=config.run(ide_globals, args))
        return _folder_follow_up(ide_globals, args, answer)
    refused = _not_allowed(ide_globals, command)
    if refused is not None:
        return refused
    script, entry = SCRIPTS[command]
    forget_engine()
    return silent.run(ide_globals, os.path.join(REPO_ROOT, "engine", script),
                      entry, args)


def _folder_follow_up(ide_globals, args, answer):
    """Setting the sync folder from here does what the dialog does after it.

    `config set` writes the property and stops, because this side may not
    import the engine (SPEC D12) and the rest is engine work: create the
    folder, give it its git rules, stamp the machine and the tool version on
    the project. A project set up this way used to come out missing
    cds-sync-pc and cds-sync-version, which is the pair load_base_dir and
    check_version_compatibility read. engine/settings.py already does all of
    it for the dialog, so it is pressed here the way every other body is,
    by path and entry name.
    """
    if (args or {}).get("key") != props.FOLDER or not answer.ok():
        return answer
    forget_engine()
    tail = silent.run(ide_globals,
                      os.path.join(REPO_ROOT, "engine", "settings.py"),
                      "folder_was_set", args)
    # The property is written either way; a failure here means the folder is
    # not usable yet, and saying so beats reporting a clean success.
    return answer if tail.ok() else tail


def _not_allowed(ide_globals, command):
    """The refusal when the project does not allow this PLC command, else None.

    Checked here rather than inside the body because the body is the thing
    being guarded: an engine module that has already been loaded and handed
    the IDE's globals has started, and "it stopped early" is not the same
    promise as "it never ran" (SPEC 6.5).
    """
    if not command.startswith(PLC_PREFIX):
        return None
    action = command[len(PLC_PREFIX):]
    reason = permit.refusal(ide_globals.get("projects"), action)
    if reason is None:
        return None
    return silent.Outcome([], "", error=reason, denied=permit.record(action))


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
