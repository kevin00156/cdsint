# -*- coding: utf-8 -*-
"""plc trace, online: log in, check what the controller says, record, judge.

SPEC 6.8 steps 4 to 9, on the trace object engine/plc_trace_setup.py made in
memory; engine/entry_plc.py runs the steps in that order. Reaching the
controller and judging its CRC are already engine/plc_trip.py's, so
TraceTrip is that trip with the trace steps added, not a second copy of it.

Each check below is here because a bench run showed what happens without it
(docs/trace-research.md): start() fails on a bad name without naming it, so
every name is read first; the runtime allocates whatever ring it is sent
until the operating system kills it, so the ring's cost is bounded before
the download; a stopped application records nothing; and a trace that
stopped itself refuses stop().

Nothing here saves the project, and nothing here waits by itself: the wait is
a function cds/ide/hold.py lends the body (SPEC D5), and the clock is an
argument, so CI runs the whole recording in no time at all.
"""
from __future__ import print_function

import os

from cds.core import settings, trace_job, trace_run, trace_types
from engine import entry, plc_crc, plc_link, plc_trace_verdict, unhandled
from engine.plc_trace_setup import TraceSetup
from engine.plc_trip import Trip, first_problem, one_line
from engine.strings import safe_str

# D7's one self-answered prompt: "The trace already exists on the device.
# Delete?" (research 7.1). Safe only while the trace's name is cdsint's alone.
OVERWRITE_PROMPT = "Strings.OverwriteExistingOnlineTrace"

# str() of session.application_state for a running application; the bench
# showed `run` and `stop`.
RUNNING = "run"

# str() of the trace editor's packet and trigger states (research 13.4).
# Only a Started trace takes stop(); a trigger's trace goes to Stopped itself.
STARTED = "Started"
STOPPED = "Stopped"
TRIGGER_REACHED = "TriggerReached"

# The IDE's words when another client holds the controller (research 3.2).
ALREADY_LOGGED_IN = "already logged in"

# Step 9 reads the CSV whether or not the job asked for one; when it did not,
# the file goes to the trip's workspace instead of beside the other outputs.
WORKSPACE_CSV = "trace.csv"

# The report's own keys (SPEC 6.8), beside the ones every plc command has.
# A run with a trigger adds "trigger".
REPORT_KEYS = ("controller", "crc", "task", "period_us", "resolution",
               "duration_s", "buffer", "files", "variables", "complete", "why")


class TraceTrip(TraceSetup):
    """One plc trace run: the trip to the controller, plus the recording."""

    def __init__(self, *args, **kwargs):
        TraceSetup.__init__(self, *args, **kwargs)
        self.session = None         # the online application, while logged in
        self.editor = None
        self.csv_path = None
        self.shown = {}             # lower-case name -> what read_value said
        self.types = {}             # lower-case name -> its IEC type, or None
        self.end_state = None       # the packet state when the wait ended

    def recording(self):
        """Log in, check, record and save; always log out (SPEC 6.8, 4 to 8)."""
        option = entry.borrowed(self.globals, "OnlineChangeOption")
        if option is None:
            return ("this IDE did not provide OnlineChangeOption, so a login "
                    "that neither downloads nor makes an online change cannot "
                    "be asked for explicitly")
        self.session = self.online.create_online_application(self.application)
        try:
            return self._log_in(option.Keep) or first_problem([
                self.names_resolve, self.types_fit, self.memory_fits,
                self.application_runs, self.size_the_buffers, self.record,
                self.save])
        finally:
            plc_link.logout(self.session)

    def _log_in(self, keep):
        """Keep: log in, applying whatever the program has that the controller
        lacks. the_program_is_unchanged has already made that nothing."""
        try:
            self.session.login(keep, False)
        except Exception as exc:
            said = one_line(exc)
            if ALREADY_LOGGED_IN in said.lower():
                return ("another client is logged in to the controller and "
                        "it takes only one, so downloading would not help: "
                        "log that client out and run again. The IDE said: "
                        + said)
            return "the login was refused: " + said
        self.note("logged in with OnlineChangeOption.Keep")
        return None

    # -- step 5: what the controller says about the names -------------------

    def names_resolve(self):
        """Every name the job uses reads on the controller. Failures by name.

        Neither the IDE nor the build checks these names; the controller is
        the only thing that does, and read_value() is where it says which.
        """
        failed = []
        for name in trace_job.named(self.job):
            try:
                shown = safe_str(self.session.read_value(name))
            except Exception as exc:
                unhandled.note(name, one_line(exc))
                failed.append("%s (%s)" % (name, one_line(exc)))
                continue
            self.shown[name.lower()] = shown
            self.types[name.lower()] = trace_types.type_of(shown)
        if failed:
            return ("%d variable(s) do not resolve on the controller: %s. "
                    "Nothing was downloaded" % (len(failed), ", ".join(failed)))
        self.note("every variable resolves on the controller")
        return None

    def types_fit(self):
        """Each name reads back as a type its role takes (SPEC 6.8)."""
        refused = trace_types.refusals(self.job, self.shown)
        for name, why in refused:
            unhandled.note(name, why)
        if refused:
            return ("%d variable(s) cannot be used as they read back: %s. "
                    "Nothing was downloaded" % (len(refused), "; ".join(
                        "%s %s" % pair for pair in refused)))
        return None

    def memory_fits(self):
        """The controller's ring fits under trace_memory_mb. None if it does."""
        limit, problem = self._memory_limit()
        if problem:
            return problem
        ring, per_variable = trace_run.buffers(
            self.found["period_us"], self.job["every_n_cycles"],
            self.job["duration_s"])
        types = [self.types[name.lower()] for name in self.job["variables"]]
        self.found["buffer"] = {
            "controller_entries": ring,
            "controller_bytes": trace_run.ring_bytes(ring, types),
            "ide_per_variable": per_variable}
        return trace_run.over_limit(ring, types, limit)

    def _memory_limit(self):
        """(trace_memory_mb from the project's settings file, None) or
        (None, why it could not be read)."""
        path = self.project_path()
        try:
            written = settings.read(settings.path_for(path)) if path else None
        except settings.Invalid as exc:
            return None, safe_str(exc)
        return settings.resolve(written)["trace_memory_mb"], None

    def application_runs(self):
        """The application is running. This command does not start it."""
        state = safe_str(getattr(self.session, "application_state", None))
        if state != RUNNING:
            return ("the application on the controller is in state %s, not "
                    "%s. A stopped application records nothing, and this "
                    "command does not start it: that would change the "
                    "controller's state, which nobody asked for"
                    % (state, RUNNING))
        return None

    def size_the_buffers(self):
        """Both buffers, through the private member found before login."""
        buffer = self.found["buffer"]
        try:
            self.set_buffers(buffer["controller_entries"],
                             buffer["ide_per_variable"])
        except Exception as exc:
            return "the trace buffers could not be set: " + one_line(exc)
        self.note("controller ring %d entries (about %d bytes), IDE buffer %d "
                  "per variable" % (buffer["controller_entries"],
                                    buffer["controller_bytes"],
                                    buffer["ide_per_variable"]))
        return None

    # -- steps 7 and 8: the recording ---------------------------------------

    def record(self):
        """Download the trace, start it, hold until it is done, stop it."""
        prompts = entry.borrowed(self.globals, "PromptResult")
        if prompts is None:
            return ("this IDE did not provide PromptResult, so the trace "
                    "download's overwrite prompt cannot be answered")
        try:
            self.editor = self.api.open_editor()
            self._download(prompts.OK)
            self.editor.start()
            try:
                holds = trace_run.wait(self.hold, self.clock,
                                       self.job["duration_s"], self._done)
            finally:
                self._stop()
        except Exception as exc:
            return "the trace did not record: " + one_line(exc)
        self.note("recorded for %s s at most (%d holds of %d ms)"
                  % (self.job["duration_s"], holds, trace_run.HOLD_MS))
        return None

    def _download(self, ok):
        """The editor's download, with D7's one prompt answered around it only.

        Set by this step, not by answer_prompts, so no other command in the
        run inherits the answer (SPEC D7).
        """
        answers = entry.borrowed(self.globals, "system").prompt_answers
        answers[OVERWRITE_PROMPT] = ok
        try:
            self.editor.download()
        finally:
            del answers[OVERWRITE_PROMPT]

    def _done(self):
        """A trace with a trigger stops itself; nothing else ends early."""
        return "trigger" in self.job and self._packet_state() == STOPPED

    def _packet_state(self):
        return safe_str(self.editor.get_packet_state())

    def _stop(self):
        """Stop the trace if it is still going; note it if it stopped itself.

        stop() on a trace that is not Started raises "Cannot stop the trace
        in the current state" (research 13.4), so the state is asked first.
        The trigger state is read before stop(), while it still says what
        the trace saw.
        """
        if "trigger" in self.job:
            reached = safe_str(self.editor.get_trigger_state())
            self.found["trigger"] = {"reached": reached == TRIGGER_REACHED}
        self.end_state = self._packet_state()
        if self.end_state == STARTED:
            self.editor.stop()
            return
        self.note("the trace was %s at the end of the wait, so it was not "
                  "stopped again" % self.end_state)

    def save(self):
        """Each requested format, plus the CSV step 9 reads either way."""
        files = dict((kind, self.job["out"] + "." + kind)
                     for kind in self.job["formats"])
        self.csv_path = files.get("csv") or os.path.join(self.workspace(),
                                                         WORKSPACE_CSV)
        path = None
        try:
            for path in sorted(set(list(files.values()) + [self.csv_path])):
                _ensure_directory(path)
                self.editor.save(plc_crc.forget(path))
        except Exception as exc:
            return ("the trace recorded but could not be saved to %s: %s"
                    % (path, one_line(exc)))
        self.found["files"] = files
        self.note("saved " + ", ".join(sorted(files.values())))
        return None

    # -- step 9: what came of it --------------------------------------------

    def verdict(self):
        """Judge the saved samples. ok only when nothing is wrong with them."""
        judged, problem = plc_trace_verdict.judged(
            self.csv_path, self.found["period_us"], self.job, self.types)
        self.found.update(judged)
        problem = self._ending_problem() or problem
        if problem:
            return self.failed(problem)
        if unhandled.any_so_far():
            return self.failed(unhandled.summary())
        return self.result(True, "trace: %d variable(s) recorded from %s, %s"
                           % (len(judged["variables"]),
                              self.found["controller"], self._judged_as()))

    def _ending_problem(self):
        """Why the trace did not end the way this run needs, or None.

        A trigger's trace has to have stopped itself; any other has to
        still be running when duration_s is up, or it recorded less than
        was asked for, and nothing in its timestamps would say so.
        """
        trigger = self.job.get("trigger")
        if trigger is None:
            if self.end_state == STARTED:
                return None
            return ("the trace was %s before duration_s %s s was up, not "
                    "%s, so it recorded less than was asked for; what it "
                    "held is saved" % (self.end_state,
                                       self.job["duration_s"], STARTED))
        if self.end_state == STOPPED:
            return None
        what = ("came, but the trace had not kept its %d samples after it"
                % trigger["post_samples"]
                if self.found["trigger"]["reached"] else "never came")
        return ("the trigger (%s, %s edge, level %s) %s within duration_s "
                "%s s; what the trace held is saved"
                % (trigger["variable"], trigger["edge"], trigger["level"],
                   what, self.job["duration_s"]))

    def _judged_as(self):
        if "record_condition" in self.job:
            return ("only in the cycles where %s was TRUE; completeness is "
                    "not judged" % self.job["record_condition"])
        return "every one complete"

    def failed(self, problem):
        """A run that stopped, or recorded short: the reason is its `why`."""
        self.found["why"] = problem
        return Trip.failed(self, problem)

    def reported(self):
        keys = REPORT_KEYS
        if self.job and "trigger" in self.job:
            keys += ("trigger",)
        return dict((key, self.found[key]) for key in keys)


def _ensure_directory(path):
    """The output's directory exists before the IDE is asked to write there."""
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
