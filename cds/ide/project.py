# -*- coding: utf-8 -*-
"""What the IDE has open right now: the project, its sync folder, the product.

Every function here takes the `projects` object the IDE injects and answers
one question about it, returning None rather than raising when the answer is
not available — a watcher must survive being asked while no project is open.
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
    """Where the .st files live, absolute, or None when it is not set.

    Straight from the settings file beside the project, resolved by the one
    rule that resolves it anywhere (cds/core/settings.folder). This is what
    the watcher puts in its registration every heartbeat, so a settings file
    somebody is halfway through editing must not raise: an unreadable one is
    reported by the next command that needs it, in full.
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
