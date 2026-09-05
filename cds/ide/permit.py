# -*- coding: utf-8 -*-
"""Which PLC commands this project allows, and the refusal when it does not.

Only the commands that touch a controller are gated, and they are gated in
two layers (SPEC D8): the project property `cds-sync-plc` says whether this
project allows the action at all, and `-y` says the caller means this
particular call. This file is the first layer.

The property is read here rather than in the engine for the same reason
cds/ide/config.py reads the others: a named property is plumbing, not
object-tree work, and the gate has to close before any engine module is
loaded — a permission check that runs inside the body it is guarding is a
check that already let the body start.

It is a policy, not a wall. Headless mode runs arbitrary IronPython inside
the IDE, so anyone determined can get past it. What it protects is the
meaning of the property: "a person sat in this IDE and decided", which is
why cds/ide/config.py refuses to write it.
"""
from __future__ import print_function

from cds.ide import project

PROPERTY = "cds-sync-plc"

# The only two values the property recognises (SPEC 6.5). A word that is not
# one of these allows nothing; it is left visible in the refusal instead of
# being corrected, because a typo the reader can see is a typo they can fix.
ACTIONS = ("connect", "download")


def granted(projects_obj):
    """The actions this project allows, in the order SPEC 6.5 lists them."""
    return [action for action in ACTIONS if action in _written(projects_obj)]


def refusal(projects_obj, action):
    """None when the action is allowed, otherwise why it is not.

    The sentence names the property, the value it currently holds and where
    to change it, because the reader's next move is to go and edit it in the
    IDE — there is no flag that answers this one.
    """
    allowed = granted(projects_obj)
    if action in allowed:
        return None
    raw = project.prop(projects_obj, PROPERTY)
    wanted = ",".join([a for a in ACTIONS if a in allowed or a == action])
    return ("this project does not allow plc %s. Its %s property is %s. Only "
            "a person in the IDE can change that: Project Information > "
            "Properties, set %s to %s. cdsint will not write it for you "
            "(SPEC 6.5)."
            % (action, PROPERTY, "not set" if raw is None else repr(raw),
               PROPERTY, wanted))


def record(action):
    """What the result record carries so the CLI can answer with exit 5.

    Separate from the sentence because the exit code is a decision and the
    sentence is prose: a caller must not have to match on wording to tell a
    refusal from a failure.
    """
    return {"property": PROPERTY, "action": action}


def _written(projects_obj):
    """The property split into words, lower-cased and stripped.

    Comma-separated because that is what SPEC 4.4 says a person types.
    Nothing is inferred from an unrecognised word: `granted` intersects with
    ACTIONS, so "download " and "DOWNLOAD" work and "downlaod" allows
    nothing.
    """
    raw = project.prop(projects_obj, PROPERTY) or ""
    return set(word.strip().lower() for word in raw.split(",") if word.strip())
