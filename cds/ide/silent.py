# -*- coding: utf-8 -*-
"""Run one of the engine/entry_*.py bodies with nobody there to click dialogs.

The bodies were written for a human: they ask "Confirm Import?" and wait. The
watcher answers those questions from the command's arguments instead, and
refuses — loudly — to guess when the caller did not say. Whether the run
worked comes from what the body returns (SPEC D11), not from what it said;
cds/ide/outcome.py is the shape that comes back.

The body is exec'd from its file rather than imported, because the stand-in
`system` has to be in its namespace before its module-level code runs, and
the menu path (engine/entry.py) has no such need. Reaching the engine by
path and by sys.modules name keeps this file free of an engine import, which
is the direction SPEC D12 forbids.

Three things have to be swapped for that to hold:

    the body's own `system`
        its namespace gets a stand-in
    codesys_ui.ask_yes_no
        a WinForms message box that never touches system.ui at all
    codesys_ui.show_sync_folder_dialog
        the first-run folder picker, which no flag can answer (SPEC 6.7)

All three go in before the body's file is exec'd, not after. A body that asks
something at module level is unusual but legal, and with the swap done second
that question reached the real dialog: a modal window on the IDE's message
loop with nobody there to close it.

Everything is put back afterwards, whether the script finished or blew up.
"""
from __future__ import print_function

import codecs
import sys

from cds.core import commands, dialogs
from cds.core.text import as_text as _text
from cds.ide.outcome import NeedsInput, Outcome
from cds.ide.tee import Tee

# Dialog title -> (the command argument that answers it, the default).
# A default of None means the caller has to say; this will not guess.
YES_NO = {
    dialogs.DELETE_ORPHANS: ("delete_orphans", False),
    dialogs.CONFIRM_IMPORT: ("yes", None),
    dialogs.CONFIRM_PLC_DOWNLOAD: ("yes", None),
}

# The name the command's flags appear under inside a body's namespace. The
# bodies were menu scripts: CODESYS drops `system` and `projects` straight
# into a script's globals and the script reads them from there, so a flag the
# menu never had is one more injected global rather than a new calling
# convention. It goes in after the body's module-level code has run, so a
# body that defines a default cannot end up reading its own placeholder.
#
# Not every flag comes this way: the ones that answer a dialog arrive through
# YES_NO above. These are the ones that were never a question — a gateway
# address, and the sync folder this run is to use (SPEC 4.2).
ARGS_GLOBAL = "command_args"

# The engine package, by name only. Importing it here would point cds/ide at
# the engine, which is the one direction SPEC D12 rules out.
UI_MODULE = "engine.codesys_ui"


class SilentUI(object):
    """Stands in for system.ui: records what would have been shown."""

    def __init__(self, args):
        self.args = args or {}
        self.messages = []

    def info(self, text):
        self._record("info", text)

    def warning(self, text):
        self._record("warning", text)

    def error(self, text):
        self._record("error", text)

    def choose(self, caption, options):
        """Pick the application named by --app. No name given, no guess."""
        labels = [_text(str(option)) for option in options]
        wanted = self.args.get("app")
        if wanted is None:
            raise NeedsInput("%s (%s)" % (caption, ", ".join(labels)), "app")
        if wanted not in labels:
            raise NeedsInput("%r is not one of: %s" % (wanted, ", ".join(labels)),
                             "app")
        return labels.index(wanted)

    def __getattr__(self, name):
        """Every other dialog needs a person. Say so instead of hanging."""
        def refuse(*args, **kwargs):
            raise NeedsInput("system.ui.%s() wanted an answer from a person"
                             % name)
        return refuse

    def _record(self, level, text):
        self.messages.append(commands.message(level, text))


class SilentSystem(object):
    """The real `system` with its .ui replaced. Everything else passes through."""

    def __init__(self, real, ui):
        self._real = real
        self.ui = ui

    def __getattr__(self, name):
        return getattr(self._real, name)


def running():
    """Is this module driving a script right now?

    Two overlapping runs would fight over sys.modules["engine.codesys_ui"]
    and sys.stdout, and one command's arguments would end up answering the
    other's dialogs. The flag is module-level rather than per
    watcher so a second caller — a Watcher built elsewhere, the MCP wrapper —
    is caught too, not just a re-entrant tick.

    It does NOT see a script the user started from the Tools menu: that goes
    through the IDE's own executor and never reaches this module. There is no
    known way to detect one from here (docs/WATCHER.md 9).
    """
    return _RUNNING["depth"] > 0


_RUNNING = {"depth": 0}


def run(ide_globals, script_path, entry, args):
    """Exec script_path, call its entry function, hand back an Outcome.

    The script is exec'd under a name that is not "__main__" so its own
    `if __name__ == "__main__"` guard does not fire and run it twice.
    """
    ui = SilentUI(args)
    silent = SilentSystem(ide_globals["system"], ui)
    namespace = dict(ide_globals)
    namespace["__name__"] = "cds_watcher_script"
    namespace["__file__"] = script_path
    namespace["system"] = silent
    _RUNNING["depth"] += 1
    try:
        return _with_stand_ins(namespace, script_path, entry, silent, ui, args)
    finally:
        _RUNNING["depth"] -= 1


def _with_stand_ins(namespace, script_path, entry, silent, ui, args):
    """Take over the dialogs, run the body, put the dialogs back."""
    try:
        undo = _install(silent, args)
    except Exception:
        # Not running the body is the safe answer. Running it with the real
        # dialogs in place would put a modal message box on the IDE's own
        # message loop with nobody there to close it, and the IDE would be
        # frozen until someone walked over to the machine.
        import traceback
        return Outcome.not_run(
            "the stand-in UI could not take over the engine's dialogs, so "
            "the command was not run:\n" + traceback.format_exc())
    tee = Tee(sys.stdout)
    sys.stdout = tee
    try:
        return _call(namespace, script_path, entry, tee, ui, args)
    finally:
        sys.stdout = tee.stream
        undo()


def _call(namespace, script_path, entry, tee, ui, args):
    """Load the body and press its button, with everything already in place."""
    try:
        _exec_file(script_path, namespace)
        namespace[ARGS_GLOBAL] = dict(args or {})
        result = namespace[entry]()
        return Outcome(ui.messages, tee.tail(), result=result)
    except NeedsInput as need:
        return Outcome(ui.messages, tee.tail(), needs=need)
    except Exception:
        import traceback
        return Outcome(ui.messages, tee.tail(), error=traceback.format_exc())


def _ui_module():
    """The engine's dialog module, loaded by name if it is not loaded yet.

    Nothing imports codesys_ui at module level -- every use of it in the
    engine is a `from engine.codesys_ui import ...` inside a function, and
    tests/test_layering.py holds it to that -- and forget_engine() empties
    sys.modules of the whole engine before every command. So on any real tick
    it is absent at this point, and the old `sys.modules.get(...) or skip`
    left the real message boxes in place without a word.

    This is the one place cds/ide reaches for an engine module, and it takes
    nothing from it: the module is loaded only so its two dialog functions
    can be swapped out and put back. The alternative is a hang inside the
    IDE, which is a worse answer to SPEC D12 than this line is.
    """
    module = sys.modules.get(UI_MODULE)
    if module is None:
        __import__(UI_MODULE)
        module = sys.modules[UI_MODULE]
    return module


def _install(silent, args):
    """Swap in the stand-in dialogs. Returns the undo.

    This used to push `silent` onto the module the IDE runs as too, because
    the shared engine modules went looking for `system` there. None of them
    does now -- they are handed it -- so writing into another module's
    namespace bought nothing and left one more thing to unwind on a path
    that already had enough.
    """
    codesys_ui = _ui_module()

    old_ui = {}
    for name, replacement in _ui_patches(args).items():
        old_ui[name] = getattr(codesys_ui, name, None)
        setattr(codesys_ui, name, replacement)

    def undo():
        for name, original in old_ui.items():
            setattr(codesys_ui, name, original)
    return undo


def _ui_patches(args):
    """The codesys_ui functions that open windows of their own."""
    return {
        "ask_yes_no": _yes_no(args),
        "show_sync_folder_dialog": _no_folder_dialog,
    }


def _no_folder_dialog(system=None, settings_path=None):
    """The first-run setup has no flag that can answer it (SPEC 6.7).

    It is a modal window on the IDE's own message loop, so opening it here
    would freeze the IDE until someone walked over to the machine. Refuse
    instead, and say what to go and do -- naming the file the dialog would
    have written, because writing that file by hand is the only other way
    past this point.
    """
    raise NeedsInput(
        "this project has no sync folder yet. Write %s with "
        "{\"sync_folder\": \"./sync\"}, pass --sync-dir to use one just for "
        "this run, or run export once from the Scripts menu and it will ask."
        % (settings_path or "<project name>.cdsint.json beside the project",))


def _yes_no(args):
    def ask_yes_no(title, message):
        if title not in YES_NO:
            raise NeedsInput("unexpected dialog %r: %s" % (title, message))
        name, default = YES_NO[title]
        given = args.get(name)
        if given is not None:
            return bool(given)
        if default is None:
            raise NeedsInput("%s: %s" % (title, message), name)
        return default
    return ask_yes_no


def _exec_file(path, namespace):
    """Compile from bytes: IronPython 2.7 rejects a coding declaration in
    unicode source, and chokes on a BOM."""
    handle = open(path, "rb")
    try:
        source = handle.read()
    finally:
        handle.close()
    if source.startswith(codecs.BOM_UTF8):
        source = source[len(codecs.BOM_UTF8):]
    exec(compile(source, path, "exec"), namespace)
