# -*- coding: utf-8 -*-
"""Which PLC commands this project allows, and the refusal when it does not.

Only the commands that touch a controller are gated, and they are gated in
two layers (SPEC D8): the `plc` list in the project's settings file says
whether this project allows the action at all, and `-y` says the caller means
this particular call. This file is the first layer.

The file is read here rather than in the engine because the gate has to close
before any engine module is loaded — a permission check that runs inside the
body it is guarding is a check that already let the body start — and reading
a JSON file next to the project is plumbing, not object-tree work (SPEC D12).

It is a policy, not a wall, and it no longer claims to be more. While the
list lived in the .project it meant "a person sat in this IDE and decided";
now it is a line in a text file, so whoever can write the file can write it,
and the real gate is `-y` (SPEC 6.5).
"""
from __future__ import print_function

import json

from cds.core import settings
from cds.ide import project

KEY = "plc"

# Logging out only releases a login, so whichever word let the session in
# is enough to let it go; demanding a fourth word would trap a login the
# project allowed.
LOGIN_WORDS = ("login",) + settings.PLC_METHODS


def words_for(action, args):
    """The words of which any one allows this command.

    A login by a method is the same act as that method's own command, so it
    needs that method's word; `login` alone is only a login.
    """
    if action == "login":
        return ((args or {}).get("method") or "login",)
    if action == "logout":
        return LOGIN_WORDS
    return (action,)


def granted(projects_obj):
    """The actions this project allows, in the order SPEC 6.5 lists them."""
    written = _written(projects_obj)
    return [action for action in settings.PLC_WORDS
            if action in written]


def refusal(projects_obj, action, args=None):
    """None when the command is allowed, otherwise why it is not.

    The sentence names the file, what is in it now and what to add, because
    the reader's next move is to open that file in an editor — there is no
    flag that answers this one.
    """
    allowed = granted(projects_obj)
    words = words_for(action, args)
    if any(word in allowed for word in words):
        return None
    wanted = [a for a in settings.PLC_WORDS
              if a in allowed or a == words[0]]
    return ("this project does not allow plc %s. Its %s list is %s in %s. "
            "Add %s to that list: %s: %s."
            % (action, KEY, json.dumps(allowed), _path(projects_obj),
               _to_add(words), json.dumps(KEY), json.dumps(wanted)))


def _to_add(words):
    if len(words) == 1:
        return words[0]
    return "one of " + ", ".join(json.dumps(word) for word in words)


def record(projects_obj, word):
    """What the result record carries so the CLI can answer with exit 5.

    Separate from the sentence because the exit code is a decision and the
    sentence is prose: a caller must not have to match on wording to tell a
    refusal from a failure. The three fields are SPEC 4.3's `denied`.
    """
    return {"file": _path(projects_obj), "key": KEY, "action": word}


def _path(projects_obj):
    """The settings file this project's answer would be written in."""
    project_path = project.path_of(projects_obj)
    if project_path is None:
        return "the project's settings file"
    return settings.path_for(project_path)


def _written(projects_obj):
    """The `plc` list, or an empty one when nothing has been written.

    A settings file that cannot be parsed raises rather than reading as an
    empty list, and cds/ide/entries.py turns that into a plain failure. The
    swallowed version was worse than no gate: the command never loads, so
    nothing else ever reads that file, and the refusal said "the list is
    empty" about a file whose real problem was a typo three lines up. Adding
    the word it told you to add changed nothing, and there was no second
    message to go on.
    """
    project_path = project.path_of(projects_obj)
    if project_path is None:
        return []
    written = settings.read(settings.path_for(project_path))
    return (written or {}).get(KEY) or []
