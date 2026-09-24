# -*- coding: utf-8 -*-
"""plc trace before the login: the gates, and the trace object in memory.

SPEC 6.8 steps 1 to 3. Everything here happens offline, so a refusal costs
the controller nothing: the flags, the job, the CRC and the IDE's download
info, the task's period, and cdsint_trace created and configured. What
happens online is engine/plc_trace.py, whose TraceTrip is this with the
recording added.

Each check is here because a bench run showed what happens without it
(docs/trace-research.md): a Keep login notices no changed program, so the
CRC has to MATCH, and the IDE's download info has to agree, or the login
downloads after all; and without the private buffer member the default ring
loses most samples on a fast task, so its absence is refused before login.
"""
from __future__ import print_function

import time

from cds.core import trace_job, trace_period, trace_run
from engine import entry, object_kind, plc_crc, plc_identity
from engine import plc_trace_buffers
from engine.ide_read import children_of, kind_of, name_of
from engine.plc_trip import Trip, one_line

# The only name this command gives a trace. D7's one self-answered prompt
# (OVERWRITE_PROMPT) is safe only while this name is cdsint's alone.
TRACE_NAME = "cdsint_trace"

# The job's resolution word -> the member of the IDE's Resolution enum.
RESOLUTIONS = {"us": "MicroSeconds", "ms": "MilliSeconds"}

# The job's edge word -> the member of the trace plug-in's edge enum, the
# names research 13.4 set.
EDGES = {"rising": "Positive", "falling": "Negative", "both": "Both"}

NO_MEMBER = (
    "this IDE's trace plug-in has no %s, the private member cdsint sets both "
    "trace buffers through. With the default ring of 100 entries a task "
    "faster than about 4 ms loses most of its samples, so nothing was "
    "recorded (SPEC 6.8, \"The buffers\"). %s exists only in memory and the "
    "project is not saved." % (plc_trace_buffers.MEMBER, TRACE_NAME))


class TraceSetup(Trip):
    """The trip to the controller, as far as a trace object in memory.

    `clock` and `buffers_for` are the two seams a test replaces: the wall
    clock the wait measures against, and the function that reaches the
    private buffer member (engine/plc_trace_buffers.py), which needs clr.
    """

    def __init__(self, args, ide_globals, clock=time.time,
                 buffers_for=plc_trace_buffers.setter_for):
        Trip.__init__(self, "trace", args, ide_globals)
        self.clock = clock
        self.buffers_for = buffers_for
        self.hold = entry.borrowed(ide_globals, trace_run.HOLD_GLOBAL)
        self.job = None
        self.application = None
        self.api = None             # the trace object, in memory only
        self.set_buffers = None     # found before login, called after step 5
        self.found.update({"task": None, "period_us": None,
                           "resolution": None, "duration_s": None,
                           "buffer": None, "files": {}, "variables": [],
                           "complete": False, "trigger": None})

    # -- before anything is touched ----------------------------------------

    def may_run(self):
        """--gateway given, and a wait lent to this run. None if both."""
        if not self.args.get("gateway"):
            return ("--gateway is required. A project that finds its "
                    "controller by name can reach the wrong one, and a trace "
                    "from the wrong controller looks exactly like a right "
                    "one, so the project's own gateway is not used (SPEC 6.6)")
        if self.hold is None:
            return ("this run cannot wait: a recording holds the script for "
                    "duration_s, and that is only allowed in a --noUI run, "
                    "where there is no window to freeze (SPEC D5)")
        return None

    def read_the_job(self):
        """The job, checked again here: the IDE side does not trust the wire."""
        self.job, problem = trace_job.normalise(self.args.get("job"))
        if problem:
            return problem
        for key in ("task", "duration_s", "resolution"):
            self.found[key] = self.job[key]
        return None

    def holds_our_download(self):
        """The controller's CRC MATCHes this copy's record. None if it does.

        A Keep login notices no changed program (research 7.4), so MATCH is
        all that stands between a trace and variables that mean something
        other than what the working copy says.
        """
        problem = self.connected(self._pull_the_crc)
        if problem:
            return problem
        answer = self.judge_crc()
        why, self.found["why"] = self.found["why"], None
        if answer != plc_crc.MATCH:
            return ("the controller's CRC is %s: %s. What it runs is not "
                    "known to be this working copy's program, so the "
                    "variables could not be trusted to mean what the project "
                    "says; run plc download -y first" % (answer, why))
        self.note("crc: %s, %s" % (answer, why))
        return None

    def the_ide_agrees(self):
        """The IDE's download info here names what the controller holds.

        MATCH alone does not stop a Keep login downloading: without these
        files beside the project it downloaded the whole application,
        unasked (engine/plc_identity.py). Also where the application this
        run traces is resolved. None when they agree.
        """
        self.application = getattr(self.projects.primary,
                                   "active_application", None)
        if self.application is None:
            return "this project has no active application to trace"
        return self.connected(self._judge_the_identity)

    def _judge_the_identity(self):
        local, problem = self.pull(plc_crc.REMOTE_APP, plc_crc.PLC_APP_NAME)
        if problem:
            return "%s; %s" % (problem, plc_identity.DOWNLOAD)
        code, problem = plc_identity.judged(
            plc_crc.read_bytes(local), self.project_path(),
            name_of(self.device_node), name_of(self.application))
        if problem:
            return problem
        self.note("download info agrees with the controller: code %s" % code)
        return None

    # -- the trace, in memory -----------------------------------------------

    def find_the_period(self):
        """The job's task and its period, from the task configuration."""
        project = self.projects.primary
        config = task_configuration(self.application)
        if config is None:
            return ("application %s has no task configuration, so there is "
                    "no task to sample in" % name_of(self.application))
        try:
            xml = object_kind.native_xml_of(project, config, recursive=True)
        except Exception as exc:
            return ("the task configuration could not be exported to read "
                    "the task's period: " + one_line(exc))
        if not xml:
            return "exporting the task configuration wrote nothing to read"
        period, problem = trace_period.task_period_us(xml, self.job["task"])
        if problem:
            return problem
        self.found["period_us"] = period
        self.note("task %s runs every %d us" % (self.job["task"], period))
        return None

    def no_trace_of_ours(self):
        """Nothing in the project is called cdsint_trace already."""
        if self.projects.primary.find(TRACE_NAME, True):
            return ("this project already has an object named %s. It is not "
                    "renamed around: this command answers the controller's "
                    "\"overwrite the trace\" prompt itself, which is only "
                    "safe while that name is cdsint's alone (SPEC D7). "
                    "Rename or delete it" % TRACE_NAME)
        return None

    def make_the_trace(self):
        """Create cdsint_trace under the application and configure it.

        The private member is looked for after create(), not before, because
        it is looked up on the type of the object create() returns; it is
        used only after step 5, when the variables' types have sized the
        ring. A refusal leaves the object in memory only; the project is
        never saved.
        """
        tracer = entry.borrowed(self.globals, "trace")
        resolution = entry.borrowed(self.globals, "Resolution")
        if tracer is None or resolution is None:
            return ("this IDE's scripting API has no trace plug-in (no "
                    "'trace' or 'Resolution' global), so nothing can record")
        try:
            self.api = tracer.create(self.application, TRACE_NAME,
                                     self.job["task"])
        except Exception as exc:
            return "%s could not be created: %s" % (TRACE_NAME, one_line(exc))
        self.set_buffers = self.buffers_for(self.api)
        if self.set_buffers is None:
            return NO_MEMBER
        return self._configure(getattr(
            resolution, RESOLUTIONS[self.job["resolution"]]))

    def _configure(self, resolution):
        job = self.job
        try:
            for name in job["variables"]:
                self.api.add_trace_variable(variableName=name)
            self.api.resolution = resolution
            self.api.every_n_cycles = job["every_n_cycles"]
            if "trigger" in job:
                self._set_trigger(job["trigger"])
            if "record_condition" in job:
                self.api.record_condition = job["record_condition"]
        except Exception as exc:
            return "%s could not be configured: %s" % (TRACE_NAME,
                                                       one_line(exc))
        self.note("%s: %d variable(s) on task %s" % (
            TRACE_NAME, len(job["variables"]), job["task"]))
        return None

    def _set_trigger(self, trigger):
        """Every trigger setting, enabled last.

        A trigger left half set makes the next start() fail without saying
        why (research 4), so all of them go in before it is switched on. The
        edge enum is the plug-in's own and not a script global, so its type
        is read off the value the new trace already holds. The level goes in
        as text, which the IDE converts to the variable's type (research 4).
        """
        api = self.api
        api.trigger_variable = trigger["variable"]
        api.trigger_edge = getattr(type(api.trigger_edge),
                                   EDGES[trigger["edge"]])
        api.trigger_level = str(trigger["level"])
        api.post_trigger_samples = trigger["post_samples"]
        api.trigger_enabled = True


def task_configuration(application):
    """The application's task configuration object, or None."""
    for child in children_of(application):
        if kind_of(child) == "task_config":
            return child
    return None
