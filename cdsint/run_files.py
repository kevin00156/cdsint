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
from cdsint.exits import Failure

if os.name == "nt":
    import msvcrt
else:
    import fcntl

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
    """One cdsint run per project at a time, for the whole of the run.

    The lock is the operating system's, taken on an open file and held until
    the file is closed: the kernel lets go of it when the process dies, so a
    run that was killed leaves nothing anybody has to judge stale. A lock
    kept in whether a file exists had to be cleared by whoever found its
    owner dead, and two runs finding it together could each clear the other.

    The file itself is never deleted. A run that opened it just before the
    holder deleted it would lock a file nobody else can see any more, and the
    next run would create and lock a second one: two holders again.
    """

    def __init__(self, project):
        self.project = project
        self.path = os.path.join(runs_dir(), project_key(project) + ".lock")
        self._fd = None

    def acquire(self):
        """Take the lock, or raise a Failure naming who has it."""
        ipc.makedirs(os.path.dirname(self.path))
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT)
        try:
            if not _lock(fd):
                raise Failure(
                    "another cdsint run is driving %s (pid %s, lock file "
                    "%s). Wait for it to finish."
                    % (self.project, self._holder().get("pid"), self.path),
                    EXIT_HEADLESS)
            _write_holder(fd, self.project)
        except BaseException:
            os.close(fd)
            raise
        self._fd = fd

    def release(self):
        if self._fd is not None:
            _unlock(self._fd)
            os.close(self._fd)
            self._fd = None

    def _holder(self):
        """What the lock file says about who holds it; only ever shown to a
        person, so a file the holder has not written yet reads as nobody."""
        try:
            return ipc.read_json(self.path) or {}
        except (ValueError, EnvironmentError):
            return {}


# Taken beyond anything the file holds: a Windows lock is mandatory, and a
# locked byte the holder's pid sits in could not be read by the run it
# refuses. Locking past the end of a file is allowed there.
_LOCK_OFFSET = 1 << 20

# What a lock somebody else holds raises as: EACCES and EDEADLOCK from
# msvcrt.locking, EAGAIN or EWOULDBLOCK from flock. Anything else is a real
# error and is let out.
_HELD = frozenset([errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK,
                   getattr(errno, "EDEADLOCK", errno.EDEADLK)])


def _lock(fd):
    """Take the lock without waiting. False when somebody else has it."""
    try:
        if os.name == "nt":
            os.lseek(fd, _LOCK_OFFSET, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in _HELD:
            return False
        raise
    return True


def _unlock(fd):
    if os.name == "nt":
        os.lseek(fd, _LOCK_OFFSET, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)


def _write_holder(fd, project):
    """Who holds the lock, for the message a refused run prints."""
    os.ftruncate(fd, 0)
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, json.dumps({"pid": os.getpid(), "started_epoch": time.time(),
                             "project": project}).encode("utf-8"))
