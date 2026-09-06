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
import time

from cds.core import ipc
from cds.core.exits import EXIT_HEADLESS, EXIT_TIMEOUT
from cds.ide.entries import REPO_ROOT
from cds.ide.headless import BEGIN_MARK, END_MARK, JOB_ENV
from cdsint import installs, lock
from cdsint.exits import Failure
from cdsint.flags import DEFAULT_TIMEOUT_S
from cdsint.report import default_report
from cdsint.report import untrusted_exit as report_untrusted_exit

# The IDE-side script this starts, in the same tree as everything else.
# REPO_ROOT rather than a second dirname chain off this file: two names for
# one place is how one of them goes stale (PRINCIPLES.md 7).
IDE_SIDE = os.path.join(REPO_ROOT, "cds", "ide", "headless.py")

KILL_GRACE_S = 5.0

# --timeout bounds one step (SPEC 4.2), so the deadline for the whole process
# has to add what the IDE spends either side of the work. What that costs is
# measured, and the numbers live in SPEC section 7 rather than here, because
# they change when a machine or an IDE version does and a copy in a comment
# would not.
#
# These two are deliberately several times the measured cost: a grace that is
# too small kills a healthy run, which is the bug this replaced, while one
# that is too large only delays the report of a launch that hung. Startup
# also swings by two to three times depending on whether the machine has run
# an IDE recently (SPEC 7), which is the reason for the margin rather than a
# tight fit.
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
        self.report_path = os.path.abspath(report or default_report(self.project))
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
        self._check_project(force_lock)
        self._note(installs.elevation_note(self.install))

    def describe(self):
        return "%s (%s)" % (self.install["name"], self.profile)

    def _note(self, text):
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
        """
        job = {"project": self.project, "report": self.report_path,
               "answers": self.answers, "sync_dir": self._sync_dir,
               "commands": [{"command": c, "args": a} for c, a in steps]}
        job_path = self.report_path + ".job.json"
        ipc.write_json(job_path, job)
        # The report path is stable across runs on purpose (report
        # .default_report keeps the file, and --report is often a fixed name
        # in a Makefile), so anything there now belongs to the last run. Read
        # as this run's answer it says "finished" for an IDE that hung on a
        # dialog and wrote nothing. stdout and stderr are already truncated
        # each launch; this makes the report agree with them.
        ipc.remove_file(self.report_path)
        deadline = self.deadline(len(steps))
        started = time.time()
        code, pid = self._launch(job_path, deadline)
        elapsed = time.time() - started
        return self._collect(code, pid, elapsed, deadline)

    def deadline(self, step_count):
        """How long this whole process may take, from what one step may take.

        --timeout means the same thing in both forms — the longest one
        command may run. What this form adds is the launch: a watcher is
        already open and this IDE is not. Deriving the process deadline
        rather than giving the headless form a default of its own keeps one
        flag with one meaning (SPEC 4.2).
        """
        return (STARTUP_GRACE_S + step_count * self.timeout
                + SHUTDOWN_GRACE_S)

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
        held = lock.held(self.project)
        if held is None:
            return
        if not force_lock:
            raise Failure(
                "%s is open in another process (lock file %s). Close it, or "
                "pass --force-lock if you believe the lock is stale."
                % (self.project, held), EXIT_HEADLESS)
        self._note("lock file present, going ahead because --force-lock: "
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
        try:
            return process.wait(timeout=deadline), process.pid
        except subprocess.TimeoutExpired:
            self._kill(process)
            return None, process.pid   # no exit code: it was killed
        except KeyboardInterrupt:
            # Leaving it would leave a --noUI process with no window,
            # holding the project's lock, findable only in Task
            # Manager. cdsint/target.py un-queues its command for the
            # same reason.
            self._kill(process)
            raise

    def _kill(self, process):
        """Stop waiting, and clean up after the process we started.

        --noUI does not stop every dialog, and one that opens with nothing to
        close it holds the process forever. Killing and saying so beats a
        caller that waits all night.

        The lock file is cleared only once the process is really gone: while
        it is alive it may still be writing the project, and a cleared lock
        would let the next run open a half-written one.
        """
        process.kill()
        try:
            process.wait(timeout=KILL_GRACE_S)
        except subprocess.TimeoutExpired:
            self._note("%s (pid %s) did not die when killed, so its lock file "
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

        Ours means there was no lock when this object was built. With
        --force-lock there may have been a real one -- another IDE with the
        project genuinely open -- and clearing that would let the next run
        open it alongside, which ends with one of the two saves lost.
        """
        if self._lock_was_there:
            self._note("the lock file was there before we started, so it is "
                       "not ours to remove: " + (lock.held(self.project) or ""))
            return
        removed, failures = lock.clear(self.project)
        for path in removed:
            self._note("removed the lock file left by the IDE we killed: "
                       + path)
        for path, exc in failures:
            self._note("could not remove the lock file %s left by the IDE we "
                       "killed: %s" % (path, exc))

    # -- afterwards ---------------------------------------------------------

    def _collect(self, code, pid, elapsed, deadline):
        """Read the report, add what only this side knows, write it back."""
        report = ipc.read_json(self.report_path) or {}
        report.update(self._annotate(report, code, pid, elapsed, deadline))
        ipc.write_json(self.report_path, report)
        return self._verdict(report, code)

    def _annotate(self, report, code, pid, elapsed, deadline):
        """The fields only this side of the launch can fill in (SPEC 6.4).

        The IDE side writes its report only after every command has been run,
        so a report carrying intended_exit is the script's own account of a
        finished run — and that outranks anything the exit code says
        afterwards. Whether the exit code can be used as a gate is therefore
        a fact to measure, not to assume: the script writes down the code it
        meant to use and this compares.
        """
        finished = report.get("intended_exit") is not None
        added = {
            "install": self.install["name"], "profile": self.profile,
            "report_path": self.report_path,
            # The IDE side's value if it got that far, because that is the
            # folder the engine read; the flag only says what was asked for.
            "sync_dir": report.get("sync_dir") or self._sync_dir,
            "elapsed_s": round(elapsed, 3),
            "pid": pid, "exit_code_actual": code, "timed_out": code is None,
            "stdout_path": self.stdout_path(),
            "stderr_path": self.stderr_path(),
            "stdout_reached": self._stdout_reached(),
            "exit_code_trusted": finished and code == report.get("intended_exit"),
        }
        if code is None:
            added["error"] = _also(report.get("error"),
                                   self._late_exit(pid, deadline) if finished
                                   else self._timed_out(pid, deadline))
        return added

    def _verdict(self, report, code):
        """The results, or the reason there are none. Says each thing once.

        A killed run's sentence is either the Failure's message or a note,
        never both: it used to be printed here and then again by
        cdsint/exits.py when the Failure carrying the same text was reported.
        Which of the two it is depends on whether the work got done — a
        report with an intended_exit is the answer, and a kill that came
        after it is only a slow shutdown (SPEC 6.4).

        A Failure carries the notes with it. There are no results on that
        path, so nothing else would ever say them, and they are exactly what
        the reader needs: a run that was killed is also a run whose lock file
        somebody has to account for.
        """
        if code is None and report.get("intended_exit") is None:
            raise Failure(report["error"], EXIT_TIMEOUT, self.notes)
        if code is None:
            self._note(report["error"])
        else:
            self._note(report_untrusted_exit(report))
        if not report.get("opened"):
            raise Failure(report.get("error")
                          or "the IDE ran but wrote no report; see "
                             + self.stdout_path(), EXIT_HEADLESS, self.notes)
        for result in report["results"]:
            # SPEC 4.3: the --project form's record says which IDE ran it,
            # which folder it took for the truth, and where the rest of the
            # story is. The notes ride along for the same reason: a --json
            # caller has no other way to hear about a lock we cleared.
            result["ide"] = report.get("ide")
            result["report_path"] = self.report_path
            result["sync_dir"] = report.get("sync_dir")
            result["notes"] = list(self.notes)
        return report["results"]

    def _timed_out(self, pid, deadline):
        """The conclusion, not just the symptom, and it goes in the report.

        A caller reading only the report file has to find "this hung" there,
        because the exit code it would otherwise reason from is the one thing
        a killed process cannot give it. This is the half of the kill with no
        report behind it, so the work itself is unaccounted for.
        """
        return ("%s did not finish within %gs and was killed (pid %s), and it "
                "wrote no report. Under --noUI that usually means a dialog "
                "opened with nothing to close it; %s has what it was doing."
                % (self.install["name"], deadline, pid, self.stdout_path()))

    def _late_exit(self, pid, deadline):
        """Killed, but the work was already done and written down.

        A report with an intended_exit means every command ran and the script
        returned; what outlived the deadline was the IDE's own shutdown.
        Calling that a timeout would throw away the answer the run produced,
        which is the whole point of writing the report before exiting.
        """
        return ("%s finished the work and wrote its report, then did not exit "
                "within %gs and was killed (pid %s). The report is the answer; "
                "the exit code is not."
                % (self.install["name"], deadline, pid))

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


def _also(existing, note):
    """Add a fact to error without losing the one already there.

    Two things can be wrong at once — the project never opened AND the
    process had to be killed — and the second must not overwrite the first.
    """
    return note if not existing else existing + "\n\n" + note


