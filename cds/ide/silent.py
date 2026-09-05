# -*- coding: utf-8 -*-
"""Run one of the engine/entry_*.py bodies with nobody there to click dialogs.

The bodies were written for a human: they ask "Confirm Import?" and wait. The
watcher answers those questions from the command's arguments instead, and
refuses — loudly — to guess when the caller did not say. Whether the run
worked comes from what the body returns (SPEC D11), not from what it said.

The body is exec'd from its file rather than imported, because the stand-in
`system` has to be in its namespace before its module-level code runs, and
the menu path (engine/entry.py) has no such need. Reaching the engine by
path and by sys.modules name keeps this file free of an engine import, which
is the direction SPEC D12 forbids.

Three things have to be swapped for that to hold:

    the body's own `system`     its namespace gets a stand-in
    `__main__.system`           the shared engine modules look there, not at
                                the caller's globals (codesys_utils 517)
    codesys_ui.ask_yes_no       WinForms message boxes that never touch
                                system.ui at all (codesys_ui 48-90)

Everything is put back afterwards, whether the script finished or blew up.
"""
from __future__ import print_function

import codecs
import collections
import sys

# Dialog title -> (the command argument that answers it, the default).
# A default of None means the caller has to say; this will not guess.
YES_NO = {
    "Delete Orphaned Files?": ("delete_orphans", False),
    "Version Mismatch Warning": ("force", False),
    "Confirm Import": ("yes", None),
}

# Answering "yes" here would open the sync-folder dialog, which needs a
# person, so carrying on means "no": keep the folder already configured.
YES_NO_CANCEL = {
    "Computer Mismatch Detected": "force",
}

STDOUT_TAIL_LINES = 200

# The engine package, by name only. Importing it here would point cds/ide at
# the engine, which is the one direction SPEC D12 rules out.
UI_MODULE = "engine.codesys_ui"


class NeedsInput(BaseException):
    """A dialog wanted an answer that the command did not carry.

    Deliberately not an Exception. This codebase wraps IDE calls in broad
    `except Exception` blocks — Project_Build.py 73 is one — that would
    swallow it and let the script carry on as though someone had clicked.
    Same reasoning as KeyboardInterrupt.
    """

    def __init__(self, question, arg=None):
        BaseException.__init__(self, question)
        self.question = question
        self.arg = arg

    def as_record(self):
        return {"question": self.question, "arg": self.arg}


class Outcome(object):
    """What came back from a script run: its verdict, words, output and needs.

    `result` is what the body returned — engine/entry.py `result()` builds it.
    """

    def __init__(self, messages, stdout_tail, needs=None, error=None,
                 result=None):
        self.messages = messages
        self.stdout_tail = stdout_tail
        self.needs = needs
        self.error = error
        self.result = result

    def ok(self):
        return not self.error_text()

    def data(self):
        """The command's own counts, or None if it did not hand any back."""
        if isinstance(self.result, dict):
            return self.result.get("data")
        return None

    def error_text(self):
        """The reason this run failed, or None. Never a silent failure."""
        if self.error:
            return self.error
        if self.needs is not None:
            return self.needs.question
        if not isinstance(self.result, dict) or "ok" not in self.result:
            # Every body ends by returning a result (SPEC D11). Coming back
            # without one means it took a give-up path that only print()s,
            # and a caller told "ok" would go on to build code that was
            # never imported.
            return ("the script returned no result; see stdout_tail for what "
                    "it printed")
        if not self.result["ok"]:
            return (self.result.get("summary")
                    or "the script reported failure without saying why")
        return None


class SilentUI(object):
    """Stands in for system.ui: records what would have been shown."""

    def __init__(self, args):
        self.args = args or {}
        self.messages = []

    def info(self, text, *rest):
        self._record("info", text)

    def warning(self, text, *rest):
        self._record("warning", text)

    def error(self, text, *rest):
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
        self.messages.append({"level": level, "text": _text(text)})


class SilentSystem(object):
    """The real `system` with its .ui replaced. Everything else passes through."""

    def __init__(self, real, ui):
        self._real = real
        self.ui = ui

    def __getattr__(self, name):
        return getattr(self._real, name)


def running():
    """Is this module driving a script right now?

    Two overlapping runs would fight over sys.modules["engine.codesys_ui"],
    __main__.system and sys.stdout, and one command's arguments would end up
    answering the other's dialogs. The flag is module-level rather than per
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
        _exec_file(script_path, namespace)
        return _call(namespace, entry, silent, ui, args)
    finally:
        _RUNNING["depth"] -= 1


def _call(namespace, entry, silent, ui, args):
    """Run the entry function with the stand-ins installed, then take them out."""
    tee = _Tee(sys.stdout)
    try:
        undo = _install(silent, ui, args)
    except Exception:
        # Not running the body is the safe answer. Running it with the real
        # dialogs in place would put a modal message box on the IDE's own
        # message loop with nobody there to close it, and the IDE would be
        # frozen until someone walked over to the machine.
        import traceback
        return Outcome(ui.messages, "", error=(
            "the stand-in UI could not take over the engine's dialogs, so "
            "the command was not run:\n" + traceback.format_exc()))
    sys.stdout = tee
    try:
        result = namespace[entry]()
        return Outcome(ui.messages, tee.tail(), result=result)
    except NeedsInput as need:
        return Outcome(ui.messages, tee.tail(), needs=need)
    except Exception:
        import traceback
        return Outcome(ui.messages, tee.tail(), error=traceback.format_exc())
    finally:
        sys.stdout = tee.stream
        undo()


def _ui_module():
    """The engine's dialog module, loaded by name if it is not loaded yet.

    Nothing imports codesys_ui at module level -- every use of it in the
    engine is a `from engine.codesys_ui import ...` inside a function -- and
    watcher._forget_engine() empties sys.modules of the whole engine before
    every command. So on any real tick it is absent at this point, and the
    old `sys.modules.get(...) or skip` left the real message boxes in place
    without a word.

    This is the one place cds/ide reaches for an engine module, and it takes
    nothing from it: the module is loaded only so its three dialog functions
    can be swapped out and put back. The alternative is a hang inside the
    IDE, which is a worse answer to SPEC D12 than this line is.
    """
    module = sys.modules.get(UI_MODULE)
    if module is None:
        __import__(UI_MODULE)
        module = sys.modules[UI_MODULE]
    return module


def _install(silent, ui, args):
    """Swap in the stand-ins the engine modules will reach for. Returns the undo.

    The dialogs are taken over first: if that cannot be done there is no
    half-installed state to unwind, because `system` has not moved yet.
    """
    codesys_ui = _ui_module()

    main = sys.modules["__main__"]
    had_system = hasattr(main, "system")
    old_system = getattr(main, "system", None)
    main.system = silent

    old_ui = {}
    for name, replacement in _ui_patches(ui, args).items():
        old_ui[name] = getattr(codesys_ui, name, None)
        setattr(codesys_ui, name, replacement)

    def undo():
        if had_system:
            main.system = old_system
        else:
            delattr(main, "system")
        for name, original in old_ui.items():
            setattr(codesys_ui, name, original)
    return undo


def _ui_patches(ui, args):
    """The codesys_ui functions that open windows of their own."""
    return {
        "ask_yes_no": _yes_no(args),
        "ask_yes_no_cancel": _yes_no_cancel(args),
        "show_compare_dialog": _no_compare_dialog(ui),
        "show_sync_folder_dialog": _no_folder_dialog,
    }


def _no_folder_dialog(*args, **kwargs):
    """The first-run setup has no flag that can answer it (SPEC 6.7).

    It is a modal window on the IDE's own message loop, so opening it here
    would freeze the IDE until someone walked over to the machine. Refuse
    instead, and say what to go and do.
    """
    raise NeedsInput("this project has no sync folder yet; set the "
                     "cds-sync-folder property in Project Information > "
                     "Properties, or run export once from the Scripts menu")


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


def _yes_no_cancel(args):
    def ask_yes_no_cancel(title, message):
        name = YES_NO_CANCEL.get(title)
        if name is None:
            raise NeedsInput("unexpected dialog %r: %s" % (title, message))
        return "no" if args.get(name) else "cancel"
    return ask_yes_no_cancel


def _no_compare_dialog(ui):
    """Compare's picker window cannot be opened here, so report its contents.

    The counts come straight from what the window would have listed; the
    per-object lines are already on stdout, so they reach stdout_tail.
    """
    def show_compare_dialog(different, new_in_ide, new_on_disk,
                            unchanged_count=0, moved=None, *rest):
        ui.info("modified %d, only in IDE %d, only on disk %d, moved %d, "
                "identical %d (nothing was changed; compare only looks)"
                % (len(different), len(new_in_ide), len(new_on_disk),
                   len(moved or []), unchanged_count))
        return None, []
    return show_compare_dialog


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


class _Tee(object):
    """Passes writes through to the real stdout and keeps the last lines."""

    def __init__(self, stream, max_lines=STDOUT_TAIL_LINES):
        self.stream = stream
        self._lines = collections.deque(maxlen=max_lines)
        self._partial = u""

    def write(self, text):
        if self.stream is not None:
            self.stream.write(text)
        parts = (self._partial + _text(text)).split(u"\n")
        self._partial = parts.pop()
        self._lines.extend(parts)

    def flush(self):
        if self.stream is not None:
            self.stream.flush()

    def tail(self):
        lines = list(self._lines)
        if self._partial:
            lines.append(self._partial)
        return u"\n".join(lines)


def _text(value):
    """Bytes or unicode in, unicode out. IronPython 2.7 hands back both."""
    if isinstance(value, type(u"")):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return type(u"")(value)
