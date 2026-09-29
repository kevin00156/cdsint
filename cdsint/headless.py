# -*- coding: utf-8 -*-
"""The `--project` form: start an IDE of our own, drive it, read the report.

Every rule below was paid for by a failed run, and SPEC 6.4 is the table of
them. The short version: this exe is a GUI program that has to be told which
profile to use, will not open a project that is already open, and can hang
forever on a dialog nobody can click — so the launch is checked before it
happens and killed when it stops answering.

The other form is cdsint/target.py. They have the same shape on purpose:
`sync_dir()` and `run(steps)`, so `verify` is written once (SPEC D2).
"""
from __future__ import print_function

import os
import subprocess
import sys
import time

from cds.core import ipc
from cds.core.exits import EXIT_HEADLESS
from cds.ide.entries import REPO_ROOT
from cds.ide.headless import JOB_ENV
from cdsint import installs, launch_result, lock, run_files
from cdsint.launch_result import KILLED_DOWNLOAD
from cdsint.exits import Failure
from cdsint.flags import DEFAULT_TIMEOUT_S
from cdsint.job_object import WINDOWS, die_with_us

# The IDE-side script this starts, in the same tree as everything else.
# REPO_ROOT rather than a second dirname chain off this file: two names for
# one place is how one of them goes stale (PRINCIPLES.md 7).
IDE_SIDE = os.path.join(REPO_ROOT, "cds", "ide", "headless.py")

# What a wheel does not carry. `pip install .` without -e, or from a git
# URL, lands cds/, cdsint/ and engine/ under site-packages and nothing else;
# the IDE side then dies inside the IDE on the missing profile, which reads
# as an IDE bug. The profile is the one file every command needs, so it is
# the one to look for.
INSTALL_ROOT_MARKER = os.path.join(REPO_ROOT, "profiles", "default.json")

KILL_GRACE_S = 5.0

# --timeout bounds one step (SPEC 4.2), so the process deadline adds what the
# IDE spends either side of the work. That cost is measured in SPEC 7, where
# the numbers live because they move with the machine and the IDE version.
# These are several times it on purpose: a grace too small kills a healthy
# run, one too large only delays the report of a hung launch, and startup
# swings two to three times with whether the machine ran an IDE recently.
STARTUP_GRACE_S = 180.0
SHUTDOWN_GRACE_S = 60.0

class Headless(object):
    """One IDE started for one job, then left to end on its own."""

    def __init__(self, project, install=None, profile=None, report=None,
                 answers=None, sync_dir=None, timeout=DEFAULT_TIMEOUT_S,
                 force_lock=False):
        self.project = os.path.abspath(project)
        self.install = installs.resolve(installs.find(), install)
        self.profile = installs.profile_of(self.install, profile)
        self.report_path = os.path.abspath(
            report or run_files.default_report(self.project))
        self.answers = answers or {}
        # Absolute from here on: the IDE side hands it to every command as an
        # override, and the IDE's working directory is not the shell's.
        self._sync_dir = os.path.abspath(sync_dir) if sync_dir else None
        self.timeout = timeout
        # Things worth saying that did not stop the run: a lock cleared, an
        # IDE that had to be killed, an exit code that cannot be trusted.
        # Collected rather than printed so cdsint/report.py can decide where
        # they go -- stderr for a person, the record for a --json caller.
        self.notes = []
        # Remembered before anything of ours could have made one, because
        # _clear_our_lock has no other way to tell its own mess from
        # somebody else's (--force-lock lets a real one through).
        self._lock_was_there = lock.held(self.project) is not None
        self._check_install_root()
        self._check_project(force_lock)
        self.note(installs.elevation_note(self.install))

    def describe(self):
        return "%s (%s)" % (self.install["name"], self.profile)

    def note(self, text):
        """Keep a sentence for the reader, if there is one to keep."""
        if text:
            self.notes.append(text)

    def sync_dir(self):
        """Only what the caller said. Reading the settings file needs the IDE.

        None means "whatever the project's settings file says", not "nowhere".
        The line that names the folder is printed after the run, from the
        report, because that is the only account of what the engine actually
        read (cdsint/report.py show_sync_dir); this is the fallback for a run
        that never got far enough to report one.
        """
        return self._sync_dir

    def run(self, steps):
        """Start the IDE, run every step in that one process, read the report.

        One launch for the whole list, not one each: starting an IDE and
        opening a project costs half a minute, and `verify` is four commands.
        The project is deliberately not closed afterwards — closing asks
        whether to save, and headless nobody can answer (SPEC 6.4).

        The launch lock is held for all of it, so a second run on this
        project is refused rather than sharing its report and its IDE's
        project (cdsint/run_files.py).
        """
        held = run_files.LaunchLock(self.project)
        held.acquire()
        job_path = None
        try:
            job_path = run_files.write_job(self.report_path, {
                "project": self.project, "report": self.report_path,
                "answers": self.answers, "sync_dir": self._sync_dir,
                "commands": [{"command": c, "args": a} for c, a in steps]})
            # The report path is stable across runs on purpose (the default
            # one is kept, and --report is often a fixed name in a Makefile),
            # so anything there now belongs to the last run. Read as this
            # run's answer it says "finished" for an IDE that hung on a
            # dialog and wrote nothing. stdout and stderr are truncated each
            # launch; this makes the report agree with them.
            ipc.remove_file(self.report_path)
            self.downloading = any(c == "plc download" for c, _a in steps)
            deadline = self.deadline(steps)
            started = time.time()
            code, pid = self._launch(job_path, deadline)
            return self._collect(code, pid, time.time() - started, deadline)
        finally:
            if job_path is not None:
                ipc.remove_file(job_path)
            held.release()

    def deadline(self, steps):
        """How long this whole process may take, from what one step may take.

        --timeout means the same thing in both forms — the longest one
        command may run. What this form adds is the launch: a watcher is
        already open and this IDE is not. Deriving the process deadline
        rather than giving the headless form a default of its own keeps one
        flag with one meaning (SPEC 4.2).
        """
        return (STARTUP_GRACE_S
                + sum(self.timeout + waits_s(args) for _command, args in steps)
                + SHUTDOWN_GRACE_S)

    # -- before the launch --------------------------------------------------

    def _check_install_root(self):
        """Refuse to start an IDE that would only die on a half-installed tree."""
        if os.path.isfile(INSTALL_ROOT_MARKER):
            return
        raise Failure(
            "%s is missing: cdsint is not running from a clone. The IDE side "
            "needs the whole tree, so install with `pip install -e .` from a "
            "checkout." % INSTALL_ROOT_MARKER, EXIT_HEADLESS)

    def _check_project(self, force_lock):
        """Refuse a project another process has open, and say where the lock is.

        CODESYS refuses it too, cleanly — "The selected project is currently
        in use by ... on ..." — even under --noUI. This check is not the
        safety net, it is the courtesy: it saves the twenty seconds of IDE
        startup and names a path the reader recognises (SPEC 6.4).
        """
        if not os.path.isfile(self.project):
            raise Failure("no such project: " + self.project, EXIT_HEADLESS)
        held = lock.held(self.project)
        if held is None:
            return
        if not force_lock:
            raise Failure(
                "%s is open in another process (lock file %s). Close it, or "
                "pass --force-lock if you believe the lock is stale."
                % (self.project, held), EXIT_HEADLESS)
        self.note("lock file present, going ahead because --force-lock: "
                   + held)

    # -- the launch ---------------------------------------------------------

    def _launch(self, job_path, deadline):
        """Start the IDE and wait for it. Returns (exit code or None, pid).

        The command line is one string, not a list. Everything downstream of
        here re-quotes an argument list at least once, and
        --profile="a name with spaces" is the shape that gets broken by it
        (SPEC 6.4). The job goes through the environment for the same family
        of reason: --scriptargs is one string split on spaces, and these
        project paths have spaces and Chinese in them.
        """
        command = '"%s" --profile="%s" --noUI --runscript="%s"' % (
            self.install["exe"], self.profile, IDE_SIDE)
        environment = dict(os.environ)
        environment[JOB_ENV] = job_path
        out = open(self.stdout_path(), "wb")
        err = open(self.stderr_path(), "wb")
        try:
            process = subprocess.Popen(command, stdout=out, stderr=err,
                                       env=environment)
        finally:
            out.close()
            err.close()
        # Kept on self: the IDE dies when the last handle to its job closes.
        self._job = die_with_us(process)
        if self._job is None and WINDOWS:
            self.note("could not tie %s (pid %s) to this process, so killing "
                       "cdsint outright would leave it running"
                       % (self.install["name"], process.pid))
        try:
            return process.wait(timeout=deadline), process.pid
        except subprocess.TimeoutExpired:
            self._kill(process)
            return None, process.pid   # no exit code: it was killed
        except KeyboardInterrupt:
            # Left alive it is a --noUI process with no window, holding the
            # project's lock, findable only in Task Manager; cdsint/target.py
            # un-queues its command for the same reason.
            self._kill(process)
            if self.downloading:
                print(KILLED_DOWNLOAD, file=sys.stderr)
            raise

    def _kill(self, process):
        """Stop waiting, and clean up after the process we started.

        --noUI does not stop every dialog, and one that opens with nothing to
        close it holds the process forever: better killed, and said so.

        The lock file is cleared only once the process is really gone: while
        it is alive it may still be writing the project, and a cleared lock
        would let the next run open a half-written one.
        """
        process.kill()
        try:
            process.wait(timeout=KILL_GRACE_S)
        except subprocess.TimeoutExpired:
            self.note("%s (pid %s) did not die when killed, so its lock file "
                       "is left alone; the next run needs --force-lock once "
                       "you are sure that process is gone"
                       % (self.install["name"], process.pid))
            return
        self._clear_our_lock()

    def _clear_our_lock(self):
        """Remove the lock the IDE we killed left behind, if it is ours.

        A project closed properly takes its own lock with it; one that was
        killed cannot. cdsint started that IDE and knows which project it
        opened, so making the caller pass --force-lock next time would be
        asking them to vouch for a mess this made (SPEC 6.4).

        Ours means there was no lock when this object was built, AND our IDE
        said it opened the project (cds/ide/headless.py writes the report
        the moment it has). With --force-lock there may have been a real
        one; and an IDE that never got the project open did not make the
        lock that appeared meanwhile -- somebody opened the project in
        another IDE. Clearing either lets the next run open it alongside,
        which ends with one of the two saves lost.
        """
        held = lock.held(self.project)
        if held is None:
            return
        if self._lock_was_there:
            self.note("the lock file was there before we started, so it is "
                       "not ours to remove: " + held)
            return
        if not (ipc.read_json(self.report_path) or {}).get("opened"):
            self.note("the IDE we killed never said it had opened the "
                       "project, so the lock file is not ours to remove: "
                       + held)
            return
        removed, failures = lock.clear(self.project)
        for path in removed:
            self.note("removed the lock file left by the IDE we killed: "
                       + path)
        for path, exc in failures:
            self.note("could not remove the lock file %s left by the IDE we "
                       "killed: %s" % (path, exc))

    # -- afterwards ---------------------------------------------------------

    def _collect(self, code, pid, elapsed, deadline):
        """Read the report, add what only this side knows, write it back."""
        report = ipc.read_json(self.report_path) or {}
        report.update(launch_result.annotate(self, report, code, pid,
                                             elapsed, deadline))
        ipc.write_json(self.report_path, report)
        return launch_result.verdict(self, report, code)

    # stdout and stderr are named after the report rather than being fixed in
    # TEMP: two runs at once would otherwise fight over one pair of files, and
    # the second would fail to delete what the first was writing.
    def stdout_path(self):
        return self.report_path + ".stdout"

    def stderr_path(self):
        return self.report_path + ".stderr"


def waits_s(args):
    """Seconds a step waits on purpose, on top of --timeout (SPEC 6.8).

    A trace records for its job's duration_s: time the caller asked for, not
    time the IDE took. Read from the step's args, not its name, so the job
    on the wire is the one place the duration is written down.
    """
    job = args.get("job")
    return job["duration_s"] if job else 0.0

