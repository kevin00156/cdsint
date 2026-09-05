# -*- coding: utf-8 -*-
"""The objects a command could not handle, by name (SPEC D13).

One register per command run. Everything in the engine that gives up on an
object writes here instead of counting it and carrying on, so the entry
bodies read one place and the caller gets names rather than a number.

Not the same as a deliberate skip. Tasks, property accessors and the kinds
whose sync_direction is "disabled" are skipped by design and belong nowhere
near this list; what goes in here is an object that should have worked and
did not.

Module state, not a collector passed down: classify_object alone has five
call sites, and threading a register through them would put the same two
lines at each and make "remember to collect it" a rule five callers have to
keep. Not keeping that rule is why the register exists — one project opened
in an IDE missing its device plugin used to turn 229 working objects into a
traceback, because four of those five call sites had a try/except and one
did not. Safe as module state because IDE-side code never starts a thread
(SPEC D5) and the watcher runs one command at a time.
"""
from __future__ import print_function

from cds.core.text import as_text as _text

_REGISTER = []


def start():
    """Forget the previous command's failures. Called once per command."""
    del _REGISTER[:]


def note(obj, reason):
    """Record that this object could not be handled, and why.

    `obj` may be an IDE object or a name that is already a string — some
    failures happen after the object has gone, with only its path left.
    """
    _REGISTER.append({"name": name_of(obj), "reason": _text(reason)})


def records():
    """[{"name", "reason"}], in the order they were hit."""
    return list(_REGISTER)


def names():
    """Just the names, for the `data` a command hands back."""
    return [record["name"] for record in _REGISTER]


def any_so_far():
    return bool(_REGISTER)


def summary():
    """One line naming them, for the message a person reads."""
    found = names()
    if not found:
        return ""
    shown = ", ".join(found[:10])
    if len(found) > 10:
        shown += ", and %d more" % (len(found) - 10)
    return "%d object(s) could not be handled: %s" % (len(found), shown)


def name_of(obj):
    """Something a person can look up in the IDE, whatever state obj is in.

    An object whose plugin is missing raises on every attribute, name
    included, so each attempt stands on its own and the last resort is a
    sentence rather than another exception.
    """
    if isinstance(obj, bytes) or isinstance(obj, type(u"")):
        return _text(obj)
    try:
        return _text(obj.get_name())
    except Exception:
        pass
    try:
        return _text(obj.name)
    except Exception:
        pass
    try:
        return _text(obj)
    except Exception:
        return "an object that will not say its name"
