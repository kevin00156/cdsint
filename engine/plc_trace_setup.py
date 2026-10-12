# -*- coding: utf-8 -*-
"""plc trace before the login: the gates, and the trace object in memory.

SPEC 6.8 steps 1 to 3. Everything here happens offline, so a refusal costs
the controller nothing: the flags, the job, the CRC and the IDE's download
info, the task's period, and cdsint_trace created and configured. What
happens online is engine/plc_trace.py, whose TraceTrip is this with the
recording added.

Each check is here because a bench run showed what happens without it
(docs/trace-research.md, docs/ethercat-research.md 5.2): a Keep login applies
whatever the working copy has that the controller lacks, by online change or
by full download, without asking. So the CRC has to MATCH, the IDE's download
info has to agree, and the IDE has to find the program unchanged since that
download; and without the private buffer member the default ring loses most
samples on a fast task, so its absence is refused before login.
"""
from __future__ import print_function

import time

from cds.core import trace_job, trace_run
from engine import entry, plc_crc, plc_identity
from engine import ide_private, trace_config
from engine.ide_read import name_of
from engine.plc_trip import Trip, one_line

# The only name this command gives a trace. D7's one self-answered prompt
# (OVERWRITE_PROMPT) is safe only while this name is cdsint's alone.
TRACE_NAME = "cdsint_trace"

NO_MEMBER = (
    "this IDE's trace plug-in has no %s, the private member cdsint sets both "
    "trace buffers through. With the default ring of 100 entries a task "
    "faster than about 4 ms loses most of its samples, so nothing was "
    "recorded (SPEC 6.8, \"The buffers\"). %s exists only in memory and the "
    "project is not saved." % (ide_private.MEMBER, TRACE_NAME))


class TraceSetup(Trip):
    """The trip to the controller, as far as a trace object in memory.

    `clock` and `buffers_for` are the two seams a test replaces: the wall
    clock the wait measures against, and the function that reaches the
    private buffer member (engine/ide_private.py), which needs clr.
    """

    def __init__(self, args, ide_globals, clock=time.time,
                 buffers_for=ide_private.setter_for):
        Trip.__init__(self, "trace", args, ide_globals)
        self.clock = clock
        self.buffers_for = buffers_for
        self.hold = entry.borrowed(ide_globals, trace_run.HOLD_GLOBAL)
        self.job = None
        self.api = None             # the trace object, in memory only
        self.set_buffers = None     # found before login, called after step 5
        self.found.update({"task": None, "period_us": None,
                           "resolution": None, "duration_s": None,
                           "buffer": None, "files": {}, "variables": [],
                           "complete": False, "trigger": None})

    # -- before anything is touched ----------------------------------------

    def may_run(self):
        """A wait lent to this run. None if there is one.

        --gateway is reach_the_device's check, as for every plc command.
        """
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

        MATCH says nobody else has downloaded to the controller since this
        copy did. Whether this copy has changed since is the_program_is_
        unchanged's question.
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
        unasked (engine/plc_identity.py). None when they agree.
        """
        return self.connected(self._judge_the_identity)

    def _judge_the_identity(self):
        local, problem = self.pull(self.remote["app"])
        if problem:
            return "%s; %s" % (problem, plc_identity.DOWNLOAD)
        code, problem = plc_identity.judged(
            plc_crc.read_bytes(local), self.project_path(),
            name_of(self.device_node), name_of(self.application))
        if problem:
            return problem
        self.note("download info agrees with the controller: code %s" % code)
        return None

    def the_program_is_unchanged(self):
        """The working copy still compiles to what was last downloaded.

        A Keep login is not "change nothing": with the download info in
        place it applied a program edited in memory and a remapped IO channel
        by online change, and a changed EtherCAT cycle by a full download
        that left the application stopped, all without a prompt (research
        12.1, as corrected; docs/ethercat-research.md 5.2). is_uptodate
        answers without a build and was false for each of those and true for
        an unchanged copy, cdsint_trace included, so it is asked before
        cdsint_trace exists. An IDE without it cannot promise the login
        changes nothing, and is refused rather than trusted.
        """
        uptodate = getattr(self.application, "is_uptodate", None)
        if uptodate is None:
            return ("this IDE's application object has no is_uptodate, so "
                    "there is no way to tell whether a Keep login would "
                    "download; nothing was logged in to")
        if not isinstance(uptodate, bool):
            # A method, or a proxy that is truthy whatever it holds, would
            # read as "unchanged" to a bare `if not`; the gate only opens on
            # an answer that can only mean yes.
            return ("this IDE's is_uptodate is %r, not true or false, so "
                    "there is no way to tell whether a Keep login would "
                    "download; nothing was logged in to" % (uptodate,))
        if not uptodate:
            return ("the working copy's program differs from what was last "
                    "downloaded (the IDE's is_uptodate is false): code, IO "
                    "mapping, device settings or libraries were changed. A "
                    "Keep login would put that change on the controller, by "
                    "online change or a full download, without asking. Save "
                    "and run plc download -y first, or undo the change")
        return None

    # -- the trace, in memory -----------------------------------------------

    def find_the_period(self):
        """The job's task and its period, from the task configuration."""
        period, problem = trace_config.task_period_us(
            self.projects.primary, self.application, self.job["task"])
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
        problem = trace_config.configure(self.api, self.job, resolution)
        if problem:
            return "%s could not be configured: %s" % (TRACE_NAME, problem)
        self.note("%s: %d variable(s) on task %s" % (
            TRACE_NAME, len(self.job["variables"]), self.job["task"]))
        return None
