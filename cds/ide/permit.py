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

from cds.core import settings
from cds.ide import project

# The only two values the list recognises (SPEC 6.5). A word that is not one
# of these is refused by cds/core/settings.py when the file is read, so
# nothing here has to guess what somebody meant.
ACTIONS = settings.PLC_ACTIONS

KEY = "plc"


def granted(projects_obj):
    """The actions this project allows, in the order SPEC 6.5 lists them."""
    written = _written(projects_obj)
    return [action for action in ACTIONS if action in written]


def refusal(projects_obj, action):
    """None when the action is allowed, otherwise why it is not.

    The sentence names the file, what is in it now and what to add, because
    the reader's next move is to open that file in an editor — there is no
    flag that answers this one.
    """
    allowed = granted(projects_obj)
    if action in allowed:
        return None
    wanted = [a for a in ACTIONS if a in allowed or a == action]
    return ("this project does not allow plc %s. Its %s list is %s in %s. "
            "Add %s to that list: \"%s\": %s."
            % (action, KEY, allowed or "empty", _path(projects_obj), action,
               KEY, "[" + ", ".join('"%s"' % a for a in wanted) + "]"))


def record(projects_obj, action):
    """What the result record carries so the CLI can answer with exit 5.

    Separate from the sentence because the exit code is a decision and the
    sentence is prose: a caller must not have to match on wording to tell a
    refusal from a failure. The three fields are SPEC 4.3's `denied`.
    """
    return {"file": _path(projects_obj), "key": KEY, "action": action}


def _path(projects_obj):
    """The settings file this project's answer would be written in."""
    project_path = project.path_of(projects_obj)
    if project_path is None:
        return "the project's settings file"
    return settings.path_for(project_path)


def _written(projects_obj):
    """The `plc` list, or an empty one when nothing has been written.

    A settings file that cannot be parsed allows nothing. It is not this
    file's job to explain why — the command itself reads the same file a
    moment later and reports the refusal in full (SPEC 4.4) — but a gate that
    opened because a file was unreadable would be no gate at all.
    """
    project_path = project.path_of(projects_obj)
    if project_path is None:
        return []
    try:
        written = settings.read(settings.path_for(project_path))
    except (settings.Invalid, IOError, OSError):
        return []
    return (written or {}).get(KEY) or []
