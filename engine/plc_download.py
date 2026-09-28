# -*- coding: utf-8 -*-
"""plc download's own steps, on top of the trip every plc command takes.

The CRC before it, the download itself, the check that it landed, and the
record of what it left: the steps only a download runs. The trip under them,
engine/plc_trip.py, is what connect and trace share with it.
"""
from __future__ import print_function

from cds.core import ipc
from engine import ide_read, plc_crc, plc_link
from engine.plc_trip import RUNNING, Trip
from engine.strings import safe_str


def state_of(session):
    """str() of the application's state, or why it could not be read, which
    left_running then reports as a state that is not running."""
    try:
        return safe_str(session.application_state)
    except Exception as exc:
        return "unknown (it could not be read: %s)" % safe_str(exc)


class DownloadTrip(Trip):
    """One plc download: the trip, and the steps that change the controller."""

    def __init__(self, action, args, ide_globals):
        Trip.__init__(self, action, args, ide_globals)
        self.held_before = None     # the controller's CRC before this download
        self.state_after = None     # the application's state once started

    # -- before it ----------------------------------------------------------

    def what_it_holds(self):
        """The controller's CRC, and nothing else. None when it answered.

        A download runs this before it writes anything, so that afterwards it
        can show the controller changed. Deliberately not the whole read-back:
        the file list and the source archive would be measured twice and
        noted twice, and neither is part of the question being asked here.
        """
        return self.connected(self._pull_what_it_holds)

    def _pull_what_it_holds(self):
        """The CRC before a download, or why no download may follow it.

        No CRC is the right answer for a controller with nothing loaded, and
        the wrong one for a controller whose fetch failed: landed() would
        then take any CRC afterwards, the one it already held included, as a
        change. Only a listing that worked can tell the two apart, and a
        listing that raised is no evidence of absence -- the fetch before it
        most likely failed on the same dropped link.
        """
        self._pull_the_crc()
        self.held_before = self.found["plc_crc"]
        if self.held_before:
            return None
        try:
            return self._unread_crc()
        except Exception as exc:
            return ("%s could not be read and the controller would not list "
                    "what it holds (%s), so a download that writes nothing "
                    "could not be told from one that lands; nothing was sent"
                    % (self.remote["crc"], safe_str(exc)))

    def _unread_crc(self):
        """Why a CRC the controller holds could not be read, or None when it
        holds none. The application's directory is looked for in its parent
        rather than listed itself, because listing a directory that is not
        there raises exactly as a dropped link does."""
        parent, application = self.remote["dir"].rsplit("/", 1)
        if application not in plc_link.names_in(self.device, parent):
            return None
        crc = plc_crc.file_name(self.remote["crc"])
        if crc not in plc_link.names_in(self.device, self.remote["dir"]):
            return None
        return ("the controller lists %s but it could not be read, so a "
                "download that writes nothing could not be told from one "
                "that lands; nothing was sent" % self.remote["crc"])

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
        in RAM and the application's .crc on the controller still holds the
        previous program, so the check afterwards would compare against the
        wrong thing and pass or fail for the wrong reason.
        """
        option = self.globals.get("OnlineChangeOption")
        if option is None:
            return ("this IDE did not provide OnlineChangeOption, so a full "
                    "download cannot be asked for explicitly")
        try:
            session = self.online.create_online_application(self.application)
        except Exception as exc:
            return ("the IDE would not make an online application of %s, so "
                    "nothing was sent: %s"
                    % (ide_read.name_of(self.application), safe_str(exc)))
        try:
            problem = self._download_on(session, option)
            if not problem:
                # Read while logged in: after the logout the session has no
                # application left to report on.
                self.state_after = state_of(session)
        finally:
            plc_link.logout(session)
        if problem:
            return problem
        self.note("download: application state %s" % self.state_after)
        return None

    def _download_on(self, session, option):
        """Log in, write the boot application, start. None when it worked.

        Named rather than let out as a traceback: "the controller refused the
        login" and "the download stopped halfway" are things that happen on
        a bench, not bugs in this file. The login is where a full download
        happens, so any failure from inside it onwards may have left the
        application stopped.
        """
        try:
            session.login(option.Never, False)
            session.create_boot_application()
            session.start()
        except Exception as exc:
            return ("the download did not complete, and the controller may "
                    "now be stopped or partly written: " + safe_str(exc))
        return None

    def left_running(self):
        """The application runs after the download. None if it does.

        Asked after the read-back and the record, not instead of them: the
        controller does hold this download, and a later connect should say
        so; but a download that leaves the machine standing still has not
        done its job, and must not exit 0.
        """
        if self.state_after == RUNNING:
            return None
        return ("the download landed but the application is in state %s, "
                "not %s, after start(): the controller is not running it"
                % (self.state_after, RUNNING))

    # -- what came of it ----------------------------------------------------

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
            return ("the download raised nothing, but afterwards %s, so there "
                    "is nothing to show it landed" % self.crc_problem)
        if now == self.held_before:
            return ("the download raised nothing, but the controller still "
                    "holds %s, the same boot application as before, so "
                    "nothing was written to it" % now)
        return None

    def remember(self):
        """Write down what this download put there, for a later connect.

        Only a download may call this. It is the whole basis of the verdict:
        nothing rebuilt locally reproduces what the controller holds, so the
        only honest reference is what cdsint itself last left there, taken at
        the moment it left it.
        """
        plc = self.found["plc_crc"]
        path = plc_crc.record_path(self.project_path())
        entry_written = {"plc_crc": plc,
                         "device": ide_read.name_of(self.device_node),
                         "downloaded_at": ipc.iso(ipc.now())}
        problem = plc_crc.remember(path, self.found["controller"],
                                   entry_written)
        if problem:
            # Not a note: a connect after this would answer UNKNOWN, or
            # DIFFERENT against an older entry, about a controller that does
            # hold this download, and send the reader to download again.
            return ("the download landed and reads back as %s, but it was "
                    "not written down, so a later connect cannot answer "
                    "MATCH for it: %s" % (plc, problem))
        self.note("recorded in %s: %s now holds %s"
                  % (path, self.found["controller"], plc))
        return None
