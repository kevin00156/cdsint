# -*- coding: utf-8 -*-
"""The lock file CODESYS keeps beside a project it has open.

One concept, read from two directions. Before a launch it answers "is this
project already open somewhere", which is why the headless form can refuse in
a quarter of a second instead of spending twenty on an IDE that would refuse
anyway. After a kill it answers "is there a lock left that we made", because
an IDE that was killed cannot take its own lock with it and the next run
would otherwise stop on a mess this tool created (SPEC 6.4).

Nothing here decides anything: cdsint/headless.py owns when to refuse and when
to clear. This file only knows where the file is and how to remove it.
"""
from __future__ import print_function

import os


def paths(project):
    """Both shapes CODESYS uses for the lock beside a project.

    lock_test.project pairs with lock_test.~u, and Shm_2026.07.29.project
    with Shm_2026.07.29.project.~u. Checking one shape leaves the gate blind
    half the time.
    """
    stem = os.path.splitext(project)[0]
    return [project + ".~u", stem + ".~u"]


def held(project):
    """The lock file that exists, or None. The first one is enough to refuse."""
    for path in paths(project):
        if os.path.exists(path):
            return path
    return None


def clear(project):
    """Remove every lock beside this project. Returns (removed, failures).

    Failures come back rather than raising: this runs while cleaning up after
    a killed process, and a lock that will not go is worth saying out loud
    but is not worth losing the run's report over.
    """
    removed, failures = [], []
    for path in paths(project):
        if not os.path.exists(path):
            continue
        try:
            os.remove(path)
        except OSError as exc:
            failures.append((path, exc))
        else:
            removed.append(path)
    return removed, failures
