# -*- coding: utf-8 -*-
"""plc download in the watcher: the --project download, through an IDE
somebody has open, leaving it as it was found (owner decision, 2026-11-20).

The steps are the download's own (engine/plc_download.py), and what it
leaves on the controller and in the CRC record is the same: the device node
is aimed at --gateway as in the --project form, so both forms reach the
controller the same way and name it the same way. That changes the open
project's device setting, and the result says so. The node could not be
checked instead: on the bench get_address() kept a value an IP aim had
overridden, find_address_by_ip answered every address with the one it had
found before, and a node found by scanning holds no IP at all (owner
decision after the bench, 2026-11-20). Three things differ, each a rule of
the IDE being somebody's rather than of the download:

- The IDE must be logged out. A login there is somebody's -- a person's, a
  plc login's, a recording plc trace's -- and the download would end it.
  The download logs out afterwards as the other form does, so the IDE is
  offline again, as it was.
- It needs --after, the change count verify reported, so that it downloads
  the project verify checked and not one another caller has changed since
  (cds/core/turns.py). The watcher refuses a stale one before this body
  runs; this refuses one that is missing, because the wire is not trusted.
- Every online call has the forwarded login handed over right before it,
  inside one nested script run (docs/trace-research.md 17.5, 17.10).
"""
from __future__ import print_function

from engine import entry, ide_private, ide_read, plc_link
from engine.plc_download import DownloadTrip
from engine.plc_trip import NO_GATEWAY, first_problem, one_line

NO_AFTER = ("--after is required in the watcher: it is the change count "
            "verify reported, and without it this would download whatever "
            "another caller has made of the project since; run verify -y "
            "and pass the count it reports")

LOGGED_IN = ("the IDE is logged in to the controller (by hand, by plc login, "
             "or for a plc trace), and a download here would end that "
             "session, so it was left alone: plc logout first, or log out "
             "in the IDE, then verify again, since a plc logout moves the "
             "change count; nothing was done")



class WatchedDownloadTrip(DownloadTrip):
    """One plc download through the watcher."""

    def __init__(self, action, args, ide_globals):
        DownloadTrip.__init__(self, action, args, ide_globals)
        self.found["logged_in"] = None
        self.sent = False   # whether send() was reached, and so logged in

    def run(self):
        """Every step inside one nested script run; then the verdict."""
        problem = ide_private.in_script_run(
            entry.borrowed(self.globals, "online"), self._through)
        return self.failed(problem) if problem else self.verdict()

    def _through(self):
        """The steps' problem. One from send() on still reports whether the
        IDE is logged in: the logout after a failed download is not read
        back by plc_link.logout, which only warns."""
        problem = first_problem(self.steps())
        if problem and self.sent and self.found["logged_in"] is None:
            self.found["logged_in"], _unread = self._logged_in()
        return problem

    def send(self):
        self.sent = True
        return DownloadTrip.send(self)

    def steps(self):
        return [
            self.has_after,          # the count verify reported
            self.reach_the_device,   # the node, already aimed at --gateway
            self.logged_out_first,   # nobody's session to end
            self.what_it_holds,      # the CRC on the controller before this
            self.send,               # download, boot application, start,
                                     # and log out again
            self.logged_out_again,   # read back, not assumed
            self.read_back,          # the CRC, the files and the archive
            self.landed,             # and the two CRCs are not the same
            self.remember,           # what it left, for a later connect
            self.left_running,       # after the record: it does hold this
        ]

    def before_online(self):
        return plc_link.hand_over_for(self)

    def connected(self, job):
        return self.before_online() or DownloadTrip.connected(self, job)

    def has_after(self):
        return None if self.args.get("after") else NO_AFTER

    # -- which controller ---------------------------------------------------

    def reach_the_device(self):
        """The --project form's resolution and aim, with the forwarded login
        rather than the IDE process's own environment (design R4)."""
        if not self.args.get("gateway"):
            return NO_GATEWAY
        problem = self.find_the_project()
        if problem:
            return problem
        self.device_node, problem = plc_link.find_device(self.projects.primary)
        if problem:
            return problem
        problem = self.name_the_application() or self.point_at_gateway()
        if problem:
            return problem
        self.note("the device node of the open project now points there; "
                  "the project is marked changed, and saving it keeps that")
        return None

    # -- whose session ------------------------------------------------------

    def logged_out_first(self):
        logged_in, problem = self._logged_in()
        if problem:
            return problem
        return LOGGED_IN if logged_in else None

    def logged_out_again(self):
        """The download logged out; the IDE has to read so."""
        logged_in, problem = self._logged_in()
        self.found["logged_in"] = logged_in
        if problem:
            return "the download landed, but " + problem
        if logged_in:
            return ("the download landed and logged out, but the IDE still "
                    "reads logged in")
        self.note("logged out again, as the IDE was before this command")
        return None

    def _logged_in(self):
        """(is_logged_in of the active application, None) or (None, why)."""
        problem = self.before_online()
        if problem:
            return None, problem
        try:
            session = self.online.create_online_application(self.application)
            return session.is_logged_in is True, None
        except Exception as exc:
            return None, ("whether %s is logged in could not be read: %s"
                          % (ide_read.name_of(self.application),
                             one_line(exc)))

