# -*- coding: utf-8 -*-
"""plc download in the watcher: the --project download, through an IDE
somebody has open, leaving it as it was found (owner decision, 2026-11-20).

The steps are the download's own (engine/plc_download.py), and what it
leaves on the controller and in the CRC record is the same. Four things
differ, and each is a rule of the IDE being somebody's rather than of the
download:

- The device node is not aimed. Aiming it rewrites the project of whoever
  has the IDE open. --gateway is still required (SPEC 6.6), and the node has
  to point there already, through the same gateway at the same node
  address, or nothing is done. The controller is named from --gateway as in
  the other form, so both forms write the same CRC record entry.
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

from engine import entry, ide_private, ide_read, plc_crc, plc_link
from engine.plc_download import DownloadTrip
from engine.plc_trip import NO_GATEWAY, first_problem, one_line
from engine.strings import safe_str

NO_AFTER = ("--after is required in the watcher: it is the change count "
            "verify reported, and without it this would download whatever "
            "another caller has made of the project since; run verify -y "
            "and pass the count it reports")

LOGGED_IN = ("the IDE is logged in to the controller (by hand, by plc login, "
             "or for a plc trace), and a download here would end that "
             "session, so it was left alone: plc logout first, or log out "
             "in the IDE; nothing was done")

NOT_AIMED = ("the device node points at %s, not at %s:%d through %s (node "
             "address %s). In the watcher the node is not re-aimed, since "
             "that rewrites the project of whoever has the IDE open: set its "
             "Communication Settings there, or download with --project; "
             "nothing was done")


class WatchedDownloadTrip(DownloadTrip):
    """One plc download through the watcher."""

    def __init__(self, action, args, ide_globals):
        DownloadTrip.__init__(self, action, args, ide_globals)
        self.found["logged_in"] = None

    def run(self):
        """Every step inside one nested script run; then the verdict."""
        problem = ide_private.in_script_run(
            entry.borrowed(self.globals, "online"),
            lambda: first_problem(self.steps()))
        return self.failed(problem) if problem else self.verdict()

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
        """The --project form's resolution, with a check where it aims."""
        if not self.args.get("gateway"):
            return NO_GATEWAY
        problem = self.find_the_project()
        if problem:
            return problem
        self.device_node, problem = plc_link.find_device(self.projects.primary)
        if problem:
            return problem
        return self.name_the_application() or self.points_at_gateway()

    def points_at_gateway(self):
        """The node already reaches --gateway. None if it does."""
        address = self.args.get("gateway")
        port = int(self.args.get("port") or plc_link.DEFAULT_DEVICE_PORT)
        gateways = list(getattr(self.online, "gateways", []) or [])
        gateway, problem = plc_link.pick_gateway(
            gateways, self.args.get("gateway_name"), address)
        if problem:
            return problem
        self.found["controller"] = plc_crc.controller_key(
            plc_link.gateway_name(gateway), address, port)
        try:
            wanted = safe_str(gateway.find_address_by_ip(address, port))
            aimed = (self.device_node.get_gateway() == gateway.guid
                     and _same(self.device_node.get_address(), wanted))
        except Exception as exc:
            return ("whether the device node points at %s:%d could not be "
                    "read, so nothing was done: %s"
                    % (address, port, one_line(exc)))
        if not aimed:
            return NOT_AIMED % (
                plc_link.node_address(self.device_node, gateways)
                or "an address it would not give", address, port,
                plc_link.gateway_name(gateway), wanted)
        self.note("the device node points at %s:%d through %s (node address "
                  "%s)" % (address, port, plc_link.gateway_name(gateway),
                           wanted))
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


def _same(node_address, wanted):
    """Two node addresses as the IDE prints them, case aside."""
    return safe_str(node_address).strip().upper() == wanted.strip().upper()
