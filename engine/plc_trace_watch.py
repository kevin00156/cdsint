# -*- coding: utf-8 -*-
"""plc trace in the watcher: through the person's login, across the ticks.

SPEC 6.8 "In the watcher". The person whose IDE it is has logged in, and
cdsint neither logs in nor out there (D8): it records the trace they named
through their session. So the gates are the ones that session leaves:
logged in, the application running, the names, trace_memory_mb, and the
trace not already recording. The CRC is reported as unknown rather than
read (SPEC 6.8): reading it takes a device connection of cdsint's own, and
closing that can end the person's session.

The watcher's timer may not wait (D5), so this file never does. start()
runs every check and starts the trace inside one nested script run, which
the online calls need from a tick (engine/ide_private.py in_script_run),
and hands back a Recording; the watcher calls its poll() once a tick until
poll() hands back the run's result.
"""
from __future__ import print_function

from engine import entry, ide_private
from engine.plc_trace import TraceTrip
from engine.plc_trip import first_problem, one_line

# stop() returns before the trace has stopped: a file saved straight after
# it ended about 60 samples early (research 15.3). The polls after a stop
# wait for is_running to go false, but not longer than this.
STOP_GRACE_S = 2.0

NEEDS_A_NAME = ("in the watcher plc trace records a trace object named with "
                "--name: it records through the login already open in this "
                "IDE, and CODESYS adds no object to an application that is "
                "logged in")
NOT_LOGGED_IN = ("the application is not logged in. In the watcher cdsint "
                 "records through the login of the person whose IDE it is "
                 "and never logs in itself (SPEC D8): log in, then run this "
                 "again")
CRC_NOT_READ = ("the controller's CRC is not read in the watcher: that takes "
                "a device connection of cdsint's own, and closing it can end "
                "the session of the person logged in through this IDE")


class WatchedTrip(TraceTrip):
    """One plc trace in the watcher, up to the moment the trace starts."""

    def start(self):
        """A Recording, or the failed result of the check that refused."""
        problem = ide_private.in_script_run(
            entry.borrowed(self.globals, "online"),
            lambda: first_problem(self.steps()))
        if problem:
            return self.failed(problem)
        return Recording(self)

    def steps(self):
        return [self.needs_a_name, self.read_the_job, self.find_the_project,
                self.name_the_application, self.take_the_named_trace,
                self.find_the_period, self.logged_in,
                self.not_recording_already, self.names_resolve,
                self.types_reported, self.types_fit, self.memory_fits,
                self.application_runs, self.size_the_buffers,
                self.report_the_program, self.start_recording]

    def needs_a_name(self):
        return None if self.named() else NEEDS_A_NAME

    def logged_in(self):
        """The person's login, which this run records through."""
        try:
            self.session = self.online.create_online_application(
                self.application)
            logged = self.session.is_logged_in
        except Exception as exc:
            return ("whether the application is logged in could not be "
                    "asked: " + one_line(exc))
        if logged is not True:
            return NOT_LOGGED_IN
        self.note("recording through the login already open in this IDE")
        return None

    def not_recording_already(self):
        """A trace the person started is theirs: taking it over would end
        their recording and lose what it held."""
        if self.api.open_editor().is_running:
            return ("%s is recording already, started in the IDE; stop it "
                    "there, or wait for it, then run this again"
                    % self.found["trace"])
        return None

    def report_the_program(self):
        """is_uptodate and the CRC are reported here, not gated (SPEC 6.8)."""
        uptodate = getattr(self.application, "is_uptodate", None)
        self.found["uptodate"] = (uptodate if isinstance(uptodate, bool)
                                  else None)
        if uptodate is False:
            self.note("the working copy differs from what was last "
                      "downloaded; the variables are read as the controller "
                      "has them")
        self.note(CRC_NOT_READ)
        return None


class Recording(object):
    """A started trace. The watcher polls it once a tick until it is done."""

    def __init__(self, trip):
        self.trip = trip
        self.started = trip.clock()
        self.stop_asked = None
        self.stopping_since = None
        self.problem = None

    def stop(self, why):
        """Ask for an end before duration_s. The next poll() acts on it."""
        if self.stop_asked is None:
            self.stop_asked = why

    def poll(self):
        """None while the trace records or settles; then the run's result.

        Never raises: whatever the IDE throws becomes the result's reason,
        so the caller is answered and the watcher takes the next command.
        """
        try:
            if self.stopping_since is None:
                if self._time_to_stop():
                    self._end()
                return None
            if self._settling():
                return None
            return self._finish()
        except Exception as exc:
            return self._broke_off(exc)

    def finish(self, why):
        """End now and answer, without waiting for the trace to settle: the
        watcher is going away and will not tick again."""
        self.stop(why)
        try:
            if self.stopping_since is None:
                self._end()
            return self._finish()
        except Exception as exc:
            return self._broke_off(exc)

    def _time_to_stop(self):
        return (self.stop_asked is not None or self.trip._done()
                or self.trip.clock() - self.started
                >= self.trip.job["duration_s"])

    def _settling(self):
        """Still stopping. A stop that failed is not waited for: whatever the
        trace is doing, it is not settling into the end it was asked for."""
        return (self.problem is None and self.trip.editor.is_running
                and self.trip.clock() - self.stopping_since < STOP_GRACE_S)

    def _end(self):
        """Stop the trace. An early stop is judged on what it recorded: the
        caller chose the length, and samples it never asked for are not
        missing."""
        trip = self.trip
        elapsed = trip.clock() - self.started
        if self.stop_asked is not None and 0 < elapsed < trip.job["duration_s"]:
            trip.found["stopped_early"] = {"after_s": round(elapsed, 3),
                                           "why": self.stop_asked}
            trip.job = dict(trip.job, duration_s=elapsed)
            trip.found["duration_s"] = round(elapsed, 3)
        self.stopping_since = trip.clock()
        try:
            trip._stop()
        except Exception as exc:
            self.problem = "the trace could not be stopped: " + one_line(exc)

    def _finish(self):
        """Save, then judge. A trace that could not be stopped is saved all
        the same: what it recorded outlives a lost login (research 15.5)."""
        saved = self.trip.save()
        problem = self.problem or saved
        return self.trip.failed(problem) if problem else self.trip.verdict()

    def _broke_off(self, exc):
        """Whatever the IDE threw, as the run's reason, with what can still
        be saved saved first."""
        self.stopping_since = self.stopping_since or self.trip.clock()
        try:
            self.trip.save()
        except Exception:
            pass    # the reason already given is the one the caller needs
        return self.trip.failed("the recording broke off: " + one_line(exc))
