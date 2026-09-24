# -*- coding: utf-8 -*-
"""Which engine body is behind each command, how to press it, what comes back.

Two callers press the same buttons: the watcher inside an IDE somebody is
using, and the headless launcher inside an IDE nobody can see. They differ in
how they are told what to do and where they put the answer, not in what
running a command means — so that part lives here rather than in both, and
`answer` is it: one command in, one result record out, however the run ended.

The bodies are engine/entry_*.py, reached by path and by sys.modules name so
this file never imports the engine, which is the direction SPEC D12 forbids.

The plc commands are the odd ones. They reach the same engine bodies the same
way, but only one of the two callers may press them and only when the
project's settings file says so, so both gates — cds/ide/permit.py and
WATCHER_REFUSES below — sit here, in front of the press.
"""
from __future__ import print_function

import os

from cds.core import commands, settings
from cds.core.engine_modules import forget_engine
from cds.core.text import as_text
from cds.ide import messages, permit, silent
from cds.ide.outcome import NeedsInput, Outcome

# The install root, the directory that holds engine/ and cds/:
# cds/ide/entries.py -> ../../
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Command -> the entry body it presses, and the function that is its button.
# These are the bodies in engine/, not the stubs the IDE menu scans. The plc
# commands share a file and differ by which function is pressed, so the
# action needs no dispatcher of its own.
SCRIPTS = {
    "export": ("entry_export.py", "main"),
    "import": ("entry_import.py", "main"),
    "compare": ("entry_compare.py", "main"),
    "discover": ("entry_discover.py", "main"),
    "build": ("entry_build.py", "main"),
    "plc connect": ("entry_plc.py", "connect"),
    "plc download": ("entry_plc.py", "download"),
    "plc trace": ("entry_plc.py", "record"),
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
COMMANDS = sorted(set(SCRIPTS) - set(WATCHER_REFUSES))

# What the two layers of the PLC gate are called on the wire, so the pieces
# either side of it — the CLI's subcommand, this table, cds/ide/permit.py —
# do not each spell the split their own way.
PLC_PREFIX = "plc "


def answer(ide_globals, cmd, started):
    """Run one command and build the result record both callers write.

    Every way a run can end is gathered here: the body came back, the body
    raised, or something asked a question nobody could answer. The watcher
    and the launcher used to hold a copy of this each, which is two places
    for a field to be forgotten and one place for it to be noticed.

    `started` has no default on purpose. It had one, and the launcher took
    it: every step of a --project run then reported elapsed_s 0.0, because
    new_result reads "now" for both ends when nobody says when it began. A
    forty-second import printed as 0.0s and nothing was wrong enough to fail.

    NeedsInput is caught even though cds/ide/silent.py already catches it
    around the body: it is a BaseException precisely so that the engine's
    broad `except Exception` blocks cannot swallow a question, and that same
    property means nothing else on the way out would catch it either.
    """
    command = cmd["command"]
    args = cmd.get("args") or {}
    try:
        outcome = run(ide_globals, command, args)
    except NeedsInput as need:
        return commands.new_result(cmd, False, started_at=started,
                                   error=need.question,
                                   needs_input=need.as_record())
    except Exception:
        import traceback
        return commands.new_result(cmd, False, started_at=started,
                                   error=traceback.format_exc())
    error = outcome.error_text()
    return commands.new_result(
        cmd, not error, started_at=started, error=error,
        messages=outcome.messages,
        stdout_tail=tail(ide_globals, command, outcome),
        data=outcome.data(),
        denied=outcome.denied,
        needs_input=None if outcome.needs is None else outcome.needs.as_record())


def run(ide_globals, command, args):
    """Run one command and hand back what it did, as a cds.ide.outcome.Outcome.

    The verdict is the body's return value (SPEC D11); its dialogs are just
    what a person would have read.
    """
    refused = _not_allowed(ide_globals, command)
    if refused is not None:
        return refused
    script, entry = SCRIPTS[command]
    forget_engine()
    return silent.run(ide_globals, os.path.join(REPO_ROOT, "engine", script),
                      entry, args)


def _not_allowed(ide_globals, command):
    """The refusal when the project does not allow this PLC command, else None.

    Checked here rather than inside the body because the body is the thing
    being guarded: an engine module that has already been loaded and handed
    the IDE's globals has started, and "it stopped early" is not the same
    promise as "it never ran" (SPEC 6.5).

    A settings file that cannot be read comes back as a failure, not a
    refusal: `denied` is what earns exit 5, and exit 5 tells the caller to go
    and add a word to the `plc` list. That is the wrong instruction for a
    file with a typo in it, and following it changes nothing — the body never
    runs, so this is the only chance anyone gets to see the real problem.
    """
    if not command.startswith(PLC_PREFIX):
        return None
    action = command[len(PLC_PREFIX):]
    projects_obj = ide_globals.get("projects")
    try:
        reason = permit.refusal(projects_obj, action)
    except settings.Invalid as bad:
        return Outcome.not_run(as_text(bad))
    if reason is None:
        return None
    return Outcome.not_run(reason, denied=permit.record(projects_obj, action))


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
