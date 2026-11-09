# -*- coding: utf-8 -*-
"""An application holds one persistent variable list; refuse a second before asking.

CODESYS answers a request for a second one with a modal dialog, and a
headless run has nobody to close it, so the command waits out its timeout
(SPEC D7). Upstream cds-text-sync met the same dialog (3.4.0, 1575eb1).
"""
from __future__ import print_function

from engine.ide_read import children_of, kind_of, name_of, parent_of

APPLICATION = "application"
FOLDER = "folder"
PERSISTENT = "persistent_gvl"


def refuse_second(container, name):
    """Raise when the application `container` is in already has a persistent list.

    Raising, not returning None, so the import names the file and this
    reason (SPEC D13) instead of a bare "could not be created".
    """
    application = _application_above(container)
    existing = _persistent_in(application) if application is not None else None
    if existing is None:
        return
    raise RuntimeError(
        "persistent variable list '%s' not created: application '%s' already "
        "has one, '%s', and CODESYS allows one per application. Put these "
        "variables in '%s' instead." % (name, name_of(application),
                                        name_of(existing), name_of(existing)))


def _application_above(node):
    """The nearest application at or above `node`, or None.

    The project at the top has no kind to read (docs/trace-research.md
    15.12), so the walk stops below it rather than asking.
    """
    parent = parent_of(node) if node is not None else None
    while parent is not None:
        if kind_of(node) == APPLICATION:
            return node
        node, parent = parent, parent_of(parent)
    return None


def _persistent_in(application):
    """The persistent list somewhere under `application`, or None.

    Folders are searched too, since one can be dragged into a folder, and
    nothing else is: a POU cannot hold one, and a child application's list
    is its own. That keeps the walk to the folders, not every object.
    """
    level = children_of(application)
    while level:
        below = []
        for child in level:
            kind = kind_of(child)
            if kind == PERSISTENT:
                return child
            if kind == FOLDER:
                below.extend(children_of(child))
        level = below
    return None
