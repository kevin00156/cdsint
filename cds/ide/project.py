# -*- coding: utf-8 -*-
"""What the IDE has open right now: the project, its sync folder, the product.

Every function here takes the `projects` object the IDE injects and answers
one question about it. No project open is None, not an exception: a watcher
must survive being asked between two projects. Anything worse than that is
the caller's to decide about, and sync_dir() says where it decided.
"""
from __future__ import print_function

import ntpath
import sys

from cds.core import settings


def path_of(projects_obj):
    """The primary project's path, or None when no project is open."""
    primary = getattr(projects_obj, "primary", None)
    path = getattr(primary, "path", None)
    return None if path is None else str(path)


def sync_dir(projects_obj):
    """Where the .st files live, absolute, or None when we cannot say.

    Straight from the settings file beside the project, resolved by the one
    rule that resolves it anywhere (cds/core/settings.folder).

    "Not set" and "the file is broken" deliberately give the same answer
    here, and this is the only place in the tool where they do. Both callers
    need one: the watcher writes this into its registration every two
    seconds, so a file somebody is halfway through editing must not take the
    watcher off the air, and the headless report writes it after the
    commands, where a broken file has already failed a command and said so in
    full. Where the difference matters — a plc command refused — nothing is
    swallowed: cds/ide/permit.py lets settings.Invalid through and
    cds/ide/entries.py turns it into a plain failure with the parse error in
    it, rather than "the plc list is empty" about a file with a typo.
    """
    project_path = path_of(projects_obj)
    if project_path is None:
        return None
    try:
        written = settings.read(settings.path_for(project_path))
    except (settings.Invalid, IOError, OSError):
        return None
    return settings.folder((written or {}).get("sync_folder"),
                           ntpath.dirname(project_path))


def ide_name():
    """Which product this is.

    sys.version alone cannot tell them apart — Delta 1.10 and Lenze 3.24 both
    report IronPython 2.7.7 — so lead with the executable's name.
    """
    # ntpath: sys.executable here is the IDE's own path, a Windows path.
    executable = ntpath.basename(getattr(sys, "executable", "") or "unknown")
    return "%s (%s)" % (executable, sys.version.replace("\n", " "))
