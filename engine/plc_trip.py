# -*- coding: utf-8 -*-
"""One trip to a controller: the objects it needs, and what it found out.

The steps engine/entry_plc.py runs in order. Split off from the two commands
because they are different jobs: the commands are the surface cds/ide has a
name for, and this is the work. The split also makes what a trip needs from
the IDE explicit -- the flags and the script run's globals arrive as
arguments rather than being read off a module the caller happened to exec.
"""
from __future__ import print_function

import os

from engine import entry, plc_crc, plc_link, unhandled
from engine.codesys_online import resolve_online
from engine.codesys_utils import resolve_projects, safe_str


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
        self._workspace = None      # made only once something is written there
        self.found = {"crc": plc_crc.UNKNOWN, "local_crc": None,
                      "plc_crc": None, "plc_files": [], "source_archive": None}

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
        self.projects = resolve_projects(None, self.globals)
        if self.projects is None or not getattr(self.projects, "primary", None):
            return "no project is open, so there is no device to talk to"
        self.online = resolve_online(self.globals)
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
        if not address:
            self.note("gateway: whatever the project already holds")
            return None
        port = int(self.args.get("port") or plc_link.DEFAULT_DEVICE_PORT)
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

    def read_back(self):
        """Connect, fetch what the controller holds, compare, report.

        Everything the controller can refuse is caught and named here. A
        traceback out of a bench command says "cdsint is broken" when what
        happened is that the machine was off.
        """
        try:
            self.device = self.online.create_online_device(self.device_node)
        except Exception as exc:
            return self.failed("could not open a connection to %s: %s"
                               % (plc_link.device_name(self.device_node),
                                  safe_str(exc)))
        try:
            try:
                self.device.connect()
            except Exception as exc:
                return self.failed(
                    "%s did not answer: %s"
                    % (plc_link.device_name(self.device_node), safe_str(exc)))
            self.found["plc_files"] = plc_link.list_remote(
                self.device, plc_crc.REMOTE_APP_DIR)
            self.found["plc_crc"] = self.pull_plc_crc()
            self.found["local_crc"] = self.build_boot_application()
            self.found["crc"] = plc_crc.compare_crc(self.found["local_crc"],
                                                    self.found["plc_crc"])
            self.found["source_archive"] = self.pull_source_archive()
        finally:
            plc_link.disconnect(self.device)
        return self.verdict()

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

    def build_boot_application(self):
        """The boot application this project compiles to, as hex, or None.

        Built from the offline application, which writes the .app and its
        .crc to the path given — the argument is what separates this from
        the call that writes one to the controller.
        """
        application = getattr(self.projects.primary, "active_application", None)
        if application is None:
            self.note("this project has no active application, so there "
                      "is nothing to compare the controller against")
            return None
        target = plc_crc.forget(os.path.join(self.workspace(),
                                             plc_crc.BOOT_NAME))
        crc_path = plc_crc.forget(os.path.join(self.workspace(),
                                               plc_crc.BOOT_CRC_NAME))
        try:
            application.create_boot_application(target)
        except Exception as exc:
            self.note("the boot application could not be built: "
                      + safe_str(exc))
            return None
        return plc_crc.crc_field(plc_crc.read_bytes(crc_path))

    def pull_source_archive(self):
        """The source archive the controller holds, when it holds one.

        Only machines that had a source download have it. Nothing here needs
        it, but a run that can retrieve the source behind the CRC it just
        compared has proved the whole claim without writing a byte, so it is
        worth the one call and the path is reported.
        """
        target = plc_crc.forget(os.path.join(self.workspace(),
                                             plc_crc.SOURCE_ARCHIVE_NAME))
        try:
            self.device.upload_source(target)
        except Exception as exc:
            self.note("no source archive on the controller: "
                      + safe_str(exc))
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
        return self.result(self.found["crc"] == plc_crc.MATCH,
                           plc_crc.verdict_line(self.action, self.found))

    def failed(self, problem):
        """A trip that never got as far as a comparison."""
        return self.result(False, "%s: %s" % (self.action, problem))

    def result(self, ok, summary):
        return entry.result(
            ok, summary, action=self.action, notes=list(self.notes),
            workspace=self._workspace, failed_objects=unhandled.names(),
            **self.found)

    def workspace(self):
        """This run's directory, made on first use.

        Made late so a trip that failed before it had anything to write
        leaves no empty directory behind and reports no path.
        """
        if self._workspace is None:
            path = getattr(getattr(self.projects, "primary", None), "path",
                           None)
            self._workspace = plc_crc.workspace(path)
        return self._workspace
