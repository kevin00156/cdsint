# -*- coding: utf-8 -*-
"""One trip to a controller: the objects it needs, and what it found out.

The steps engine/entry_plc.py runs in order. Split off from the two commands
because they are different jobs: the commands are the surface cds/ide has a
name for, and this is the work. The split also makes what a trip needs from
the IDE explicit -- the flags and the script run's globals arrive as
arguments rather than being read off a module the caller happened to exec.

Nothing here builds a boot application. It used to, so that the result could
be held against the controller's -- engine/plc_crc.py has the bench
measurements that say why those two can never agree, and why the offline
value moves every run anyway.
"""
from __future__ import print_function

import os

from cds.core import ipc
from engine import entry, plc_crc, plc_link, unhandled
from engine import ide_read
from engine.strings import safe_str


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
        self.notes = []             # what a reader needs to reproduce this
        self.held_before = None     # the controller's CRC before this download
        self._workspace = None      # made only once something is written there
        self.found = {"crc": plc_crc.UNKNOWN, "why": None, "plc_crc": None,
                      "plc_files": [], "source_archive": None,
                      "controller": plc_crc.PROJECT_GATEWAY, "recorded": None}

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
        """Resolve everything a controller conversation needs. None if ready."""
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
        return self.point_at_gateway()

    def point_at_gateway(self):
        """Aim the device at --gateway, or leave the project's own settings."""
        address = self.args.get("gateway")
        port = int(self.args.get("port") or plc_link.DEFAULT_DEVICE_PORT)
        self.found["controller"] = plc_crc.controller_key(address, port)
        if not address:
            self.note("gateway: whatever the project already holds")
            return None
        note, problem = plc_link.aim_at_gateway(self.online, self.device_node,
                                                address, port)
        if problem:
            return problem
        self.note(note)
        return None

    # -- the destructive half ----------------------------------------------

    def send(self):
        """Full download, boot application, start. None when it worked.

        OnlineChangeOption.Never is not a preference: an online change keeps
        the running state, and the whole point of a download from a pipeline
        is that every initialisation runs again. The second argument is
        delete_foreign_apps, and False is deliberate — removing applications
        that belong to somebody else is not part of "put this one on".

        create_boot_application() with no argument writes it *on the
        controller*, which is a different call from the one that writes a
        boot application to a local path. Without it the download only lands
        in RAM and PlcLogic/Application/Application.crc still holds the
        previous program, so the check afterwards would compare against the
        wrong thing and pass or fail for the wrong reason.
        """
        application = getattr(self.projects.primary, "active_application", None)
        if application is None:
            return "this project has no active application to download"
        option = self.globals.get("OnlineChangeOption")
        if option is None:
            return ("this IDE did not provide OnlineChangeOption, so a full "
                    "download cannot be asked for explicitly")
        session = self.online.create_online_application(application)
        try:
            session.login(option.Never, False)
            session.create_boot_application()
            session.start()
        except Exception as exc:
            # Named rather than let out as a traceback: "the controller
            # refused the login" and "the download stopped halfway" are
            # things that happen on a bench, not bugs in this file.
            return "the download did not complete: " + safe_str(exc)
        finally:
            plc_link.logout(session)
        self.note("download: application state %s"
                  % safe_str(getattr(session, "application_state", "unknown")))
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

    def what_it_holds(self):
        """The controller's CRC, and nothing else. None when it answered.

        A download runs this before it writes anything, so that afterwards it
        can show the controller changed. Deliberately not the whole read-back:
        the file list and the source archive would be measured twice and
        noted twice, and neither is part of the question being asked here.
        """
        return self.connected(self._pull_the_crc)

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
            self.device, plc_crc.REMOTE_APP_DIR)
        self.found["source_archive"] = self.pull_source_archive()
        return None

    def landed(self):
        """Did the download change what the controller holds? None if it did.

        Every compile stamps a fresh identity into the boot application, so
        two downloads of the same project leave two different CRCs on the
        controller — measured on the bench, where the value moved on every
        download. An unchanged CRC therefore means nothing was written, and a
        download that says "no error" without having landed is exactly the
        silent failure the read-back exists to catch. It is the only evidence
        available: nothing built locally reproduces what the controller
        holds, so there is nothing else to compare the result against.
        """
        now = self.found["plc_crc"]
        if not now:
            return ("the download raised nothing, but the controller has no "
                    "%s afterwards, so there is nothing to show it landed"
                    % plc_crc.REMOTE_CRC)
        if now == self.held_before:
            return ("the download raised nothing, but the controller still "
                    "holds %s, the same boot application as before, so "
                    "nothing was written to it" % now)
        return None

    def pull_plc_crc(self):
        """The controller's own Application.crc, as hex, or None.

        Absent is an answer, not an error: a controller with nothing loaded
        has no such file. It still fails the command, because "cannot tell"
        must not read the same as "matches".
        """
        local = plc_crc.forget(os.path.join(self.workspace(),
                                            plc_crc.PLC_CRC_NAME))
        try:
            self.device.upload_file(plc_crc.REMOTE_CRC, local, True)
        except Exception as exc:
            self.note("%s could not be fetched: %s"
                      % (plc_crc.REMOTE_CRC, safe_str(exc)))
            return None
        return plc_crc.crc_field(plc_crc.read_bytes(local))

    def pull_source_archive(self):
        """The source archive the controller holds, when it holds one.

        Only machines that had a source download have it. Nothing here needs
        it, but a run that can retrieve the source behind the CRC it just
        read has proved the whole claim without writing a byte, so it is
        worth the one call and the path is reported.
        """
        target = plc_crc.forget(os.path.join(self.workspace(),
                                             plc_crc.SOURCE_ARCHIVE_NAME))
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
                      % _one_line(safe_str(exc)))
            return None
        return target if os.path.isfile(target) else None

    # -- what came of it ----------------------------------------------------

    def remember(self):
        """Write down what this download put there, for a later connect.

        Only a download may call this. It is the whole basis of the verdict:
        nothing rebuilt locally reproduces what the controller holds, so the
        only honest reference is what cdsint itself last left there, taken at
        the moment it left it.
        """
        plc = self.found["plc_crc"]
        if not plc:
            self.note("nothing was written down about this download, so a "
                      "later connect will have nothing to compare against")
            return
        path = plc_crc.record_path(self.project_path())
        entry_written = {"plc_crc": plc,
                         "device": ide_read.name_of(self.device_node),
                         "downloaded_at": ipc.iso(ipc.now())}
        if plc_crc.remember(path, self.found["controller"], entry_written):
            self.note("recorded in %s: %s now holds %s"
                      % (path, self.found["controller"], plc))

    def verdict(self):
        """The result record, with the CRC comparison as its gate (SPEC 6.6).

        DIFFERENT and UNKNOWN both fail. compare gets to report differences
        and still be ok because verify is there to turn its counts into a
        verdict; nothing wraps these two commands, so the exit code has to be
        the verdict, and a caller that reads only the exit code is exactly
        the caller SPEC 6.6 has in mind.
        """
        path = plc_crc.record_path(self.project_path())
        records = plc_crc.read_records(path)
        self.found["recorded"] = records.get(self.found["controller"])
        answer, why = plc_crc.judge(self.found["recorded"],
                                    self.found["plc_crc"])
        self.found["crc"] = answer
        self.found["why"] = why
        return self.result(answer == plc_crc.MATCH,
                           plc_crc.verdict_line(self.action, self.found))

    def failed(self, problem):
        """A trip that never got as far as a comparison."""
        return self.result(False, "%s: %s" % (self.action, problem))

    def result(self, ok, summary):
        return entry.result(
            ok, summary, action=self.action, notes=list(self.notes),
            workspace=self._workspace, failed_objects=unhandled.names(),
            **self.found)

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


def _one_line(text):
    """One line of an exception's words: these arrive with a CRLF inside."""
    return " ".join(safe_str(text).split())
