# -*- coding: utf-8 -*-
"""One trip to a controller: the objects it needs, and what it found out.

The steps engine/entry_plc.py runs in order. Split off from the two commands
because they are different jobs: the commands are the surface cds/ide has a
name for, and this is the work. The split also makes what a trip needs from
the IDE explicit -- the flags and the script run's globals arrive as
arguments rather than being read off a module the caller happened to exec.
The steps only a download takes are engine/plc_download.py's, and a trace's
are engine/plc_trace_setup.py's and engine/plc_trace.py's.

Nothing here builds a boot application. It used to, so that the result could
be held against the controller's -- engine/plc_crc.py has the bench
measurements that say why those two can never agree, and why the offline
value moves every run anyway.
"""
from __future__ import print_function

import os

from engine import entry, plc_crc, plc_link, unhandled
from engine import ide_read
from engine.strings import safe_str

# Every plc command names its controller. One found by the project's device
# name can be the wrong one (two soft PLCs can report the same host name),
# and what the wrong one answers passes every check made of it: a download's
# read-back, a connect's MATCH, a trace's samples (SPEC 6.6).
NO_GATEWAY = ("--gateway is required. A controller found by the project's "
              "device name can be the wrong one, and what the wrong one "
              "answers looks exactly like a right one (SPEC 6.6)")

# str() of session.application_state for a running application; the bench
# showed `run` and `stop`. A download must leave it so, and a trace needs it.
RUNNING = "run"


class Trip(object):
    """One plc command: the objects it needs, and what it found out.

    Held together rather than passed around because every step after the
    first needs most of what the ones before it resolved, and a chain of
    six-argument calls hides which step is the one that failed.
    """

    def __init__(self, action, args, ide_globals):
        self.action = action
        self.globals = ide_globals
        self.args = args or {}
        self.projects = None
        self.online = None
        self.device_node = None     # the device in the project tree
        self.device = None          # the live connection to it
        self.application = None     # the project's active application
        self.remote = None          # where the controller keeps its files
        self.notes = []             # what a reader needs to reproduce this
        self.held_before = None     # the controller's CRC before this download
        self._workspace = None      # made only once something is written there
        self.found = {"crc": plc_crc.UNKNOWN, "why": None, "plc_crc": None,
                      "plc_files": [], "source_archive": None,
                      "controller": None, "recorded": None}

    def note(self, text):
        """Record one step, and say it now rather than at the end.

        Printed as it happens because stdout is the only channel a --noUI run
        has, and a run that never reaches its result has no other way to say
        where it stopped: four bench runs were killed at 360 seconds each
        having printed nothing but the headless BEGIN mark, and locating them
        took a separate probe that wrote a file per step.
        """
        self.notes.append(text)
        print("plc %s: %s" % (self.action, text))

    # -- getting there ------------------------------------------------------

    def reach_the_device(self):
        """Resolve everything a controller conversation needs. None if ready.

        --gateway is checked first, before anything is switched or aimed:
        the CLI refuses it too, but the IDE side does not trust the wire.
        """
        if not self.args.get("gateway"):
            return NO_GATEWAY
        self.projects = entry.borrowed(self.globals, "projects")
        if self.projects is None or not getattr(self.projects, "primary", None):
            return "no project is open, so there is no device to talk to"
        self.online = entry.borrowed(self.globals, "online")
        if self.online is None:
            return ("the CODESYS 'online' API is not reachable from this "
                    "script run, so nothing can connect to a controller")
        note, problem = plc_link.silence_credential_dialogs(self.online,
                                                            self.globals)
        if problem:
            return problem
        self.note(note)
        self.device_node, problem = plc_link.find_device(self.projects.primary)
        if problem:
            return problem
        return self.name_the_application() or self.point_at_gateway()

    def name_the_application(self):
        """Find the active application, and so where the controller keeps
        its files, which are named after it. None when there is one."""
        self.application = getattr(self.projects.primary,
                                   "active_application", None)
        if self.application is None:
            return ("this project has no active application, so there is "
                    "nothing on the controller to ask about")
        self.remote = plc_crc.remote_files(ide_read.name_of(self.application))
        return None

    def point_at_gateway(self):
        """Aim the device at --gateway. None when it is aimed."""
        address = self.args.get("gateway")
        port = int(self.args.get("port") or plc_link.DEFAULT_DEVICE_PORT)
        self.found["controller"] = plc_crc.controller_key(address, port)
        note, problem = plc_link.aim_at_gateway(self.online, self.device_node,
                                                address, port)
        if problem:
            return problem
        self.note(note)
        return None

    # -- reading it back ----------------------------------------------------

    def connected(self, job):
        """Open a device connection, run job, close it. The problem, or None.

        Everything the controller can refuse is caught and named here. A
        traceback out of a bench command says "cdsint is broken" when what
        happened is that the machine was off.
        """
        try:
            self.device = self.online.create_online_device(self.device_node)
        except Exception as exc:
            return ("could not open a connection to %s: %s"
                    % (ide_read.name_of(self.device_node), safe_str(exc)))
        try:
            try:
                self.device.connect()
            except Exception as exc:
                return ("%s did not answer: %s"
                        % (ide_read.name_of(self.device_node),
                           safe_str(exc)))
            return job()
        finally:
            plc_link.disconnect(self.device)

    def read_back(self):
        """Connect and fetch everything. None when the controller answered."""
        return self.connected(self._pull_everything)

    def _pull_the_crc(self):
        self.held_before = self.found["plc_crc"]
        self.found["plc_crc"] = self.pull_plc_crc()
        return None

    def _pull_everything(self):
        self._pull_the_crc()
        self.found["plc_files"] = plc_link.list_remote(
            self.device, self.remote["dir"])
        self.found["source_archive"] = self.pull_source_archive()
        return None

    def pull_plc_crc(self):
        """The controller's own .crc for this application, as hex, or None.

        Absent is an answer, not an error: a controller with nothing loaded
        has no such file. It still fails the command, because "cannot tell"
        must not read the same as "matches".
        """
        local, problem = self.pull(self.remote["crc"])
        if problem:
            self.note(problem)
            return None
        return plc_crc.crc_field(plc_crc.read_bytes(local))

    def pull(self, remote):
        """Fetch one controller file into the workspace (plc_crc.local_name).

        (local path, None), or (None, why it could not be fetched). The old
        copy is removed first, so a call that returns without writing reads
        as "nothing", not as the last run's file.
        """
        try:
            local = plc_crc.forget(os.path.join(self.workspace(),
                                                plc_crc.local_name(remote)))
        except plc_crc.Stale as exc:
            return None, safe_str(exc)
        try:
            self.device.upload_file(remote, local, True)
        except Exception as exc:
            return None, "%s could not be fetched: %s" % (remote,
                                                          safe_str(exc))
        return local, None

    def pull_source_archive(self):
        """The source archive the controller holds, when it holds one.

        Only machines that had a source download have it. Nothing here needs
        it, but a run that can retrieve the source behind the CRC it just
        read has proved the whole claim without writing a byte, so it is
        worth the one call and the path is reported.
        """
        try:
            target = plc_crc.forget(os.path.join(self.workspace(),
                                                 plc_crc.SOURCE_ARCHIVE_NAME))
        except plc_crc.Stale as exc:
            self.note("the source archive was not fetched: " + safe_str(exc))
            return None
        try:
            self.device.upload_source(target)
        except Exception as exc:
            # The IDE's own words for this are "Value cannot be null.
            # Parameter name: path", which tells a reader nothing. They are
            # still carried, at the end and on one line, because the plain
            # sentence in front of them is a reading of the failure and the
            # reading could be wrong.
            self.note("no source archive to fetch: nothing has been source-"
                      "downloaded to this controller (the IDE said: %s)"
                      % one_line(safe_str(exc)))
            return None
        return target if os.path.isfile(target) else None

    # -- what came of it ----------------------------------------------------

    def verdict(self):
        """The result record, with the CRC comparison as its gate (SPEC 6.6).

        DIFFERENT and UNKNOWN both fail. compare gets to report differences
        and still be ok because verify is there to turn its counts into a
        verdict; nothing wraps these two commands, so the exit code has to be
        the verdict, and a caller that reads only the exit code is exactly
        the caller SPEC 6.6 has in mind.
        """
        answer = self.judge_crc()
        return self.result(answer == plc_crc.MATCH,
                           plc_crc.verdict_line(self.action, self.found))

    def judge_crc(self):
        """Hold the controller's CRC against this copy's record. The answer.

        Also fills in `crc`, `why` and `recorded`, which is what a reader of
        the report audits the answer by.
        """
        path = plc_crc.record_path(self.project_path())
        records = plc_crc.read_records(path)
        self.found["recorded"] = records.get(self.found["controller"])
        answer, why = plc_crc.judge(self.found["recorded"],
                                    self.found["plc_crc"], self.remote["crc"])
        self.found["crc"] = answer
        self.found["why"] = why
        return answer

    def failed(self, problem):
        """A trip that never got as far as a comparison."""
        return self.result(False, "%s: %s" % (self.action, problem))

    def result(self, ok, summary):
        return entry.result(
            ok, summary, action=self.action, notes=list(self.notes),
            workspace=self._workspace, failed_objects=unhandled.names(),
            **self.reported())

    def reported(self):
        """What this command's report carries of what it found. All of it.

        engine/plc_trace.py narrows it: the trace report has a shape of its
        own (SPEC 6.8), and the CRC bookkeeping it did on the way is not in it.
        """
        return self.found

    def project_path(self):
        """This run's project file on disk, or None when it was never saved."""
        return getattr(getattr(self.projects, "primary", None), "path", None)

    def workspace(self):
        """This run's directory, made on first use.

        Made late so a trip that failed before it had anything to write
        leaves no empty directory behind and reports no path.
        """
        if self._workspace is None:
            self._workspace = plc_crc.workspace(self.project_path())
        return self._workspace


def first_problem(steps):
    """Run steps until one reports a problem. That problem, or None."""
    for step in steps:
        problem = step()
        if problem:
            return problem
    return None


def one_line(text):
    """One line of an exception's words: these arrive with a CRLF inside."""
    return " ".join(safe_str(text).split())
