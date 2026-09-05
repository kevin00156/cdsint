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
import re
import subprocess
import sys
import tempfile
import time

from cds.core import ipc
from cds.ide.headless import BEGIN_MARK, END_MARK, JOB_ENV
from cdsint import installs
from cdsint.exits import (EXIT_FAILED, EXIT_HEADLESS, EXIT_OK, EXIT_TIMEOUT,
                          Failure)

# The install root: this file is <root>/cdsint/headless.py, and the IDE-side
# script it starts is in the same tree.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDE_SIDE = os.path.join(ROOT, "cds", "ide", "headless.py")

KILL_GRACE_S = 5.0

# Report file names come from project names, and those have spaces, Chinese
# and punctuation in them.
_SAFE = re.compile(r"[^A-Za-z0-9._-]")


class Headless(object):
    """One IDE started for one job, then left to end on its own."""

    def __init__(self, project, install=None, profile=None, report=None,
                 answers=None, sync_dir=None, timeout=120.0, force_lock=False):
        self.project = os.path.abspath(project)
        self.install = installs.resolve(installs.find(), install)
        self.profile = installs.profile_of(self.install, profile)
        self.report_path = os.path.abspath(report or _default_report(self.project))
        self.answers = answers or {}
        self._sync_dir = sync_dir
        self.timeout = timeout
        self._check_project(force_lock)
        self._warn_about_elevation()

    def describe(self):
        return "%s (%s)" % (self.install["name"], self.profile)

    def sync_dir(self):
        """Only what the caller said. What the project holds needs the IDE."""
        return self._sync_dir

    def run(self, steps):
        """Start the IDE, run every step in that one process, read the report.

        One launch for the whole list, not one each: starting an IDE and
        opening a project costs half a minute, and `verify` is four commands.
        The project is deliberately not closed afterwards — closing asks
        whether to save, and headless nobody can answer (SPEC 6.4).
        """
        job = {"project": self.project, "report": self.report_path,
               "answers": self.answers, "sync_dir": self._sync_dir,
               "commands": [{"command": c, "args": a} for c, a in steps]}
        job_path = self.report_path + ".job.json"
        ipc.write_json(job_path, job)
        started = time.time()
        code, pid = self._launch(job_path)
        elapsed = time.time() - started
        return self._collect(code, pid, elapsed)

    # -- before the launch --------------------------------------------------

    def _check_project(self, force_lock):
        """Refuse a project another process has open, and say where the lock is.

        CODESYS refuses it too, cleanly — "The selected project is currently
        in use by ... on ..." — even under --noUI. This check is not the
        safety net, it is the courtesy: it saves the twenty seconds of IDE
        startup and names a path the reader recognises (SPEC 6.4).
        """
        if not os.path.isfile(self.project):
            raise Failure("no such project: " + self.project, EXIT_HEADLESS)
        locks = [path for path in _lock_paths(self.project)
                 if os.path.exists(path)]
        if not locks:
            return
        if not force_lock:
            raise Failure(
                "%s is open in another process (lock file %s). Close it, or "
                "pass --force-lock if you believe the lock is stale."
                % (self.project, locks[0]), EXIT_HEADLESS)
        print("warning: lock file present, going ahead because --force-lock: "
              + locks[0], file=sys.stderr)

    def _warn_about_elevation(self):
        """Say who asked for elevation before the launch fails without saying."""
        if self.install["run_as_admin"]:
            print("warning: %s is marked RUNASADMIN in %s, so this launch will "
                  "fail unless this shell is elevated"
                  % (self.install["exe"], self.install["run_as_admin"]),
                  file=sys.stderr)

    # -- the launch ---------------------------------------------------------

    def _launch(self, job_path):
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
        try:
            return process.wait(timeout=self.timeout), process.pid
        except subprocess.TimeoutExpired:
            return self._kill(process), process.pid

    def _kill(self, process):
        """A hang is the answer, not an accident: something wants clicking.

        --noUI does not stop every dialog, and one that opens with nothing to
        close it holds the process forever. Killing and saying so beats a
        caller that waits all night.
        """
        process.kill()
        try:
            process.wait(timeout=KILL_GRACE_S)
        except subprocess.TimeoutExpired:
            pass
        return None

    # -- afterwards ---------------------------------------------------------

    def _collect(self, code, pid, elapsed):
        """Read the report, add what only this side knows, write it back."""
        report = ipc.read_json(self.report_path) or {}
        report.update({
            "install": self.install["name"], "profile": self.profile,
            "report_path": self.report_path, "elapsed_s": round(elapsed, 3),
            "pid": pid, "exit_code_actual": code, "timed_out": code is None,
            "stdout_path": self.stdout_path(),
            "stderr_path": self.stderr_path(),
            "stdout_reached": self._stdout_reached(),
        })
        # Whether the exit code can be used as a gate is a fact to measure,
        # not to assume: the script writes down the code it meant to use and
        # this compares (SPEC 6.4).
        intended = report.get("intended_exit")
        report["exit_code_trusted"] = (intended is not None and code == intended)
        if code is None:
            report["error"] = self._timed_out(pid)
        ipc.write_json(self.report_path, report)
        if code is None:
            raise Failure(report["error"], EXIT_TIMEOUT)
        self._say_if_untrusted(report)
        if not report.get("opened"):
            raise Failure(report.get("error")
                          or "the IDE ran but wrote no report; see "
                             + self.stdout_path(), EXIT_HEADLESS)
        for result in report["results"]:
            # SPEC 4.3: the --project form's record says which IDE ran it and
            # where the rest of the story is.
            result["ide"] = report.get("ide")
            result["report_path"] = self.report_path
        return report["results"]

    def _timed_out(self, pid):
        """The conclusion, not just the symptom, and it goes in the report.

        A caller reading only the report file has to find "this hung" there,
        because the exit code it would otherwise reason from is the one thing
        a killed process cannot give it.
        """
        return ("%s did not finish within %gs and was killed (pid %s). Under "
                "--noUI that usually means a dialog opened with nothing to "
                "close it; %s has what it was doing."
                % (self.install["name"], self.timeout, pid, self.stdout_path()))

    def _say_if_untrusted(self, report):
        if report.get("exit_code_trusted") or report.get("intended_exit") is None:
            return
        print("warning: %s meant to exit %s and the shell saw %s, so the exit "
              "code cannot be used as a gate here — read %s instead"
              % (self.install["name"], report["intended_exit"],
                 report["exit_code_actual"], self.report_path), file=sys.stderr)

    def _stdout_reached(self):
        """Both marks, not just the file: half the output is not the output."""
        try:
            with open(self.stdout_path(), "rb") as handle:
                text = handle.read().decode("utf-8", "replace")
        except (IOError, OSError):
            return False
        return BEGIN_MARK in text and END_MARK in text

    # stdout and stderr are named after the report rather than being fixed in
    # TEMP: two runs at once would otherwise fight over one pair of files, and
    # the second would fail to delete what the first was writing.
    def stdout_path(self):
        return self.report_path + ".stdout"

    def stderr_path(self):
        return self.report_path + ".stderr"


def exit_code(results):
    return EXIT_OK if all(r.get("ok") for r in results) else EXIT_FAILED


def _lock_paths(project):
    """Both shapes CODESYS uses for the lock file beside a project.

    lock_test.project pairs with lock_test.~u, and Shm_2026.07.29.project
    with Shm_2026.07.29.project.~u. Checking one shape leaves the gate blind
    half the time.
    """
    stem = os.path.splitext(project)[0]
    return [project + ".~u", stem + ".~u"]


def _default_report(project):
    """Somewhere stable to put the report when the caller did not say.

    Named after the project so two projects verified side by side do not
    overwrite each other's answer, and kept rather than deleted because it is
    the only full record of what the IDE did.
    """
    stem = os.path.splitext(os.path.basename(project))[0]
    return os.path.join(tempfile.gettempdir(), "cdsint",
                        _SAFE.sub("_", stem) + ".json")
