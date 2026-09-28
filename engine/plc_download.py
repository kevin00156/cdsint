# -*- coding: utf-8 -*-
"""plc download's own steps, on top of the trip every plc command takes.

The CRC before it, the download itself, the check that it landed, and the
record of what it left: the steps only a download runs. The trip under them,
engine/plc_trip.py, is what connect and trace share with it.
"""
from __future__ import print_function

from cds.core import ipc
from engine import ide_read, plc_crc, plc_link
from engine.plc_trip import Trip
from engine.strings import safe_str


class DownloadTrip(Trip):
    """One plc download: the trip, and the steps that change the controller."""

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
        change. Only the listing can tell the two apart, so a CRC that could
        not be read is looked for there.
        """
        self._pull_the_crc()
        if self.found["plc_crc"]:
            return None
        listed = plc_link.names_in(self.device, self.remote["dir"])
        if listed is None:
            # No such directory: nothing is loaded, so any CRC is a change.
            return None
        if plc_crc.file_name(self.remote["crc"]) not in listed:
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
        session = self.online.create_online_application(self.application)
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
            return ("the download raised nothing, but the controller has no "
                    "%s afterwards, so there is nothing to show it landed"
                    % self.remote["crc"])
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
