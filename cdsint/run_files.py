# -*- coding: utf-8 -*-
"""The files a headless run owns besides the project: report, job, launch lock.

Each is named so that two runs cannot share it by accident. The default
report is named after the project's full path, not its file name, because
C:\\ci\\branch-a\\line.project and C:\\ci\\branch-b\\line.project are two
projects with one name. The job file is made fresh for every run and deleted
after it. And the launch lock keeps a second run off a project the first one
is still driving: CODESYS's own .~u lock only appears once the IDE has opened
the project, twenty seconds in, and two runs started together both pass that
check and then fight over the report, the job and the project.
"""
from __future__ import print_function

import errno
import hashlib
import json
import os
import re
import tempfile
import time

from cds.core import ipc
from cds.core.exits import EXIT_HEADLESS
from cdsint import process
from cdsint.exits import Failure

# Report file names come from project names, and those have spaces, Chinese
# and punctuation in them.
_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def runs_dir():
    """Where reports and launch locks go when the caller did not say."""
    return os.path.join(tempfile.gettempdir(), "cdsint")


def project_key(project):
    """The project's name for a person, and a short hash for the machine.

    normcase first: on Windows C:\\P\\Line.project and c:\\p\\line.project
    are one project and must get one lock.
    """
    full = os.path.normcase(os.path.abspath(project))
    digest = hashlib.sha1(full.encode("utf-8")).hexdigest()[:8]
    stem = os.path.splitext(os.path.basename(project))[0]
    return "%s-%s" % (_SAFE.sub("_", stem), digest)


def default_report(project):
    """Somewhere stable to put a run's report when the caller did not say.

    Named after the project, so two projects verified side by side do not
    overwrite each other's answer even when their files share a name, and
    kept rather than deleted because it is the only full record of what
    the IDE did.
    """
    return os.path.join(runs_dir(), project_key(project) + ".json")


def write_job(report_path, job):
    """A job file of this run's own, beside its report. The caller deletes it."""
    directory = os.path.dirname(report_path)
    ipc.makedirs(directory)
    handle, path = tempfile.mkstemp(prefix="cdsint-", suffix=".job.json",
                                    dir=directory)
    os.close(handle)
    ipc.write_json(path, job)
    return path


class LaunchLock(object):
    """One cdsint run per project at a time, for the whole of the run."""

    def __init__(self, project):
        self.project = project
        self.path = os.path.join(runs_dir(), project_key(project) + ".lock")
        self.held = False

    def acquire(self):
        """Take the lock, or raise a Failure naming who has it.

        Returns a sentence when it had to clear a lock left by a run that
        is gone, None otherwise.
        """
        ipc.makedirs(os.path.dirname(self.path))
        if self._create():
            return None
        holder = self._holder()
        if process.running(holder.get("pid"), holder.get("started_epoch")) \
                is not False:
            raise Failure(
                "another cdsint run is driving %s (pid %s, lock file %s). "
                "Wait for it to finish; if no such run exists, delete the "
                "lock file." % (self.project, holder.get("pid"), self.path),
                EXIT_HEADLESS)
        ipc.remove_file(self.path)
        if not self._create():
            raise Failure("another cdsint run took %s just now (lock file "
                          "%s)" % (self.project, self.path), EXIT_HEADLESS)
        return ("cleared the launch lock of a cdsint run that is gone "
                "(pid %s): %s" % (holder.get("pid"), self.path))

    def release(self):
        if self.held:
            ipc.remove_file(self.path)
            self.held = False

    def _create(self):
        """O_EXCL: exactly one of two runs racing for the file gets it."""
        try:
            handle = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                return False
            raise
        with os.fdopen(handle, "w") as out:
            json.dump({"pid": os.getpid(), "started_epoch": time.time(),
                       "project": self.project}, out)
        self.held = True
        return True

    def _holder(self):
        """What the lock says. Unreadable counts as held: it may be a run
        that has created the file and not yet written it."""
        try:
            return ipc.read_json(self.path) or {}
        except (ValueError, EnvironmentError):
            return {}
