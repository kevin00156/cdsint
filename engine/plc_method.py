# -*- coding: utf-8 -*-
"""plc login --method: the watcher's logins that do change the controller.

A plain login (engine/plc_session.py) refuses whatever would change the
controller; these are the two ways the caller asks for that change instead
(design 2026-10-21-watcher-online 5.2, 5.3). Each is one OnlineChangeOption
and nothing else: a download is always a full one, and an online change that
cannot be made is refused, never carried out as a download (research 17.2).

Split from SessionTrip because these steps are the ones that write to the
controller and to the CRC record; the session's own steps never do.
"""
from __future__ import print_function

from cds.core import settings
from engine import plc_crc
from engine.plc_download import state_of
from engine.plc_session import CHANGED, ONLINE_CHANGE, SessionTrip
from engine.plc_trip import RUNNING, one_line

# The OnlineChangeOption member each --method logs in with. Never, as the
# --project download has it; ONLINE_CHANGE says why that one.
OPTIONS = {"download": "Never", "online_change": ONLINE_CHANGE}

# The application states the bench showed (research 17.7).
STATES = (RUNNING, "stop")


class MethodTrip(SessionTrip):
    """One plc login --method."""

    def __init__(self, action, args, ide_globals):
        SessionTrip.__init__(self, action, args, ide_globals)
        self.method = self.args.get("method")
        self.held_before = None     # the controller's CRC before the change

    def known_method(self):
        """A method this version has. The gate lets through a word the list
        allows, and a hand-written command can carry one that is a word but
        no method, which must not be read as a plain login."""
        if self.method in settings.PLC_METHODS:
            return None
        return ("--method %s is not one of %s; nothing was done"
                % (self.method, ", ".join(settings.PLC_METHODS)))

    def logged_out_first(self):
        """A method logs in itself: over a live session it would be a second
        path to the same thing, so the caller logs out first (design 5.2)."""
        if self.found["logged_in"] is not True:
            return None
        self.found["state"] = state_of(self.session)
        return ("already logged in, application %s; --method %s logs in "
                "itself, so log out first (plc logout) and run again; "
                "nothing was done" % (self.found["state"], self.method))

    def method_applies(self):
        """What the login will change, or why it may not be made. Offline.

        A download applies whatever differs, and even when nothing does: the
        caller asked for one. An online change needs the IDE to say it can
        carry the difference; with nothing different it changes nothing.
        """
        # Its problem (no is_uptodate) is not a refusal here: uptodate stays
        # None, which counts as changed, so the boot application is written
        # and the record cleaned as for any change; Force still refuses
        # rather than downloads.
        self.read_the_change()
        if self.method == "download":
            self.changes = "download"
            return None
        if self.found["online_change_possible"] is not True:
            self.found["methods"] = ["download"]
            return ("the IDE does not say an online change can carry what "
                    "differs (is_online_change_possible is %s), so only "
                    "--method download -y applies it (full download, leaves "
                    "the application stopped); nothing was done"
                    % self.found["online_change_possible"])
        self.changes = ("nothing" if self.found["uptodate"] is True
                        else "online_change")
        return None

    # -- the controller, before it changes ----------------------------------

    def crc_before(self):
        """The controller's CRC, over a device connection of its own: the
        download has no identity check to read it in. Never a refusal: a
        CRC not read only widens what forget_the_record removes."""
        problem = self.connected(self._read_the_crc)
        if problem:
            self.note(problem)
        return None

    def _holds_this_download(self):
        """The identity check, reading the CRC on the same connection."""
        self._read_the_crc()
        return SessionTrip._holds_this_download(self)

    def _read_the_crc(self):
        self.held_before, _unread = self.pull_plc_crc()
        return None

    def keeps_its_state(self):
        """An online change keeps the state it found (research 17.7), so the
        state read now is what must read back. A reading that is no state,
        as a session not yet logged in may give, is noted, not expected."""
        before = state_of(self.session)
        if before in STATES:
            self.expected["state"] = before
        else:
            self.note("the state before the online change read %s, so it is "
                      "not compared afterwards" % before)
        return None

    def forget_the_record(self):
        """No CRC record entry may answer MATCH after this change (design
        5.6, R5).

        Removed rather than rewritten: the new CRC would need a device
        connection while logged in. Only the entries recording the CRC the
        controller held before can match afterwards: a download or a boot
        application always moves it, and without a boot application it does
        not move at all (research 17.7). The record's keys cannot name this
        controller (plc_crc.drop_records), so when that CRC was not read,
        every entry goes. Before the login, so one that fails halfway leaves
        no MATCH either.
        """
        if self.changes == "nothing":
            return None
        held = self.held_before
        path = plc_crc.record_path(self.project_path())
        removed, problem = plc_crc.drop_records(
            path, lambda entry: held is None or _records(entry, held))
        if problem:
            return ("the CRC record could not be updated, and after this %s "
                    "it could answer MATCH for a controller that holds "
                    "something else; nothing was done: %s"
                    % (self.method, problem))
        if removed:
            self.note("removed %s from the CRC record in %s: a plc connect "
                      "answers UNKNOWN for %s until the --project plc "
                      "download -y records again"
                      % (_which(held), path, ", ".join(removed)))
        return None

    def log_in_by_method(self):
        return self.log_in_with(OPTIONS[self.method])

    def write_boot_application(self):
        """Unless --no-boot-app, or nothing changed: without it a restart of
        the controller brings back the program it held before (research
        17.7)."""
        if self.args.get("no_boot_app") is True or self.changes == "nothing":
            return None
        problem = self.hand_over()
        if problem:
            return self._unbooted(problem)
        try:
            self.session.create_boot_application()
        except Exception as exc:
            return self._unbooted(one_line(exc))
        self.found["boot_application"] = True
        self.note("boot application written")
        return None

    def _unbooted(self, why):
        return ("logged in and %s, but the boot application was not written, "
                "so a restart of the controller brings back what it held "
                "before: %s" % (CHANGED[self.changes], why))


def _records(entry, held):
    """The entry says the controller holds `held`."""
    return isinstance(entry, dict) and entry.get("plc_crc") == held


def _which(held):
    if held is None:
        return ("every entry, since the controller's CRC could not be read "
                "before the change")
    return "the entries recording %s, the CRC it held before" % held
