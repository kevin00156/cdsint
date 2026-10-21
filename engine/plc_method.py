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
from engine.plc_trip import one_line

# The OnlineChangeOption member each --method logs in with. Never, as the
# --project download has it; ONLINE_CHANGE says why that one.
OPTIONS = {"download": "Never", "online_change": ONLINE_CHANGE}


class MethodTrip(SessionTrip):
    """One plc login --method."""

    def __init__(self, action, args, ide_globals):
        SessionTrip.__init__(self, action, args, ide_globals)
        self.method = self.args.get("method")

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

    def forget_the_record(self):
        """Clear the CRC record before the controller changes (design 5.6, R5).

        Cleared rather than rewritten: the new CRC would need a device
        connection while logged in, and the record's keys cannot name the
        controller the device node points at (plc_crc.clear_records). Before
        the login, so that one that fails halfway leaves no MATCH either.
        """
        if self.changes == "nothing":
            return None
        path = plc_crc.record_path(self.project_path())
        cleared, problem = plc_crc.clear_records(path)
        if problem:
            return ("the CRC record could not be cleared, and after this %s "
                    "it could answer MATCH for a controller that holds "
                    "something else; nothing was done: %s"
                    % (self.method, problem))
        if cleared:
            self.note("cleared the CRC record in %s (%s): a plc connect "
                      "answers UNKNOWN until a plc download -y records again"
                      % (path, ", ".join(cleared)))
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
