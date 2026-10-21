# -*- coding: utf-8 -*-
"""The watcher's own session with the controller: log in, log out.

The person whose IDE it is is not at it, so the watcher logs the active
application in and out itself (design 2026-10-21-watcher-online). What it
logs in to is whatever the device node points at, as the IDE's own Login
button does; there is no --gateway here.

A plain login never changes the controller. It logs in with Keep, and Keep
applies any difference by itself, so the login happens only when the IDE
finds nothing changed and the controller holds this copy's last download
(engine/plc_keep.py); otherwise nothing is done and the report names the
--method values that would apply the change.

Two rules for every online call (docs/trace-research.md 17.5, 17.10): the
credentials are handed over and the logon dialog switched off immediately
before it, because credentials handed over earlier went stale and a dialog
nobody answers holds the IDE forever; and it runs inside the command's one
nested script run, because the watcher calls from a timer tick (15.2).

A command is a list of steps (engine/entry_plc.py). A step answers None to
go on, a problem to fail, or Done to end early with success, so a command
that differs is a different list rather than a branch in here.
"""
from __future__ import print_function

from engine import entry, ide_private, plc_keep, plc_link
from engine.plc_download import state_of
from engine.plc_trip import Trip, first_problem, one_line

# The data every session command reports.
REPORT_KEYS = ("logged_in", "state", "address", "changed", "boot_application",
               "uptodate", "online_change_possible", "methods")

# What found["changed"] says, as the summary says it.
CHANGED = {"nothing": "nothing on the controller changed",
           "download": "downloaded in full",
           "online_change": "changed online"}

# The cure for a controller that does not hold this copy's download: the
# watcher refuses plc download and points here instead.
WATCHER_DOWNLOAD = ("use plc login --method download -y to put this working "
                    "copy on it")


class Done(object):
    """A step's answer that ends the command early, successfully: there was
    nothing to do, and `summary` says why."""

    def __init__(self, summary):
        self.summary = summary


class SessionTrip(Trip):
    """One login, logout, run or stop through the IDE's own application."""

    def __init__(self, action, args, ide_globals):
        Trip.__init__(self, action, args, ide_globals)
        self.session = None
        self.expected = {}          # what found must read back as afterwards
        self.found.update({"logged_in": None, "state": None, "address": None,
                           "changed": "nothing", "boot_application": False,
                           "uptodate": None, "online_change_possible": None,
                           "methods": []})

    def run(self, steps):
        """Every step inside one nested script run; then the answer."""
        answer = ide_private.in_script_run(
            entry.borrowed(self.globals, "online"),
            lambda: first_problem(steps))
        if isinstance(answer, Done):
            return self.result(True, "%s: %s" % (self.action, answer.summary))
        if answer:
            return self.failed(answer)
        return self.verdict()

    # -- before any online call ---------------------------------------------

    def plain_login_only(self):
        """--method is not built yet; refused rather than read as a plain
        login, which is the one thing it must never become."""
        method = self.args.get("method")
        if method:
            return ("--method %s is not available in this version; nothing "
                    "was done" % method)
        return None

    def find_the_device(self):
        """The device node, and where it points (research 17.6)."""
        self.device_node, problem = plc_link.find_device(self.projects.primary)
        if problem:
            return problem
        self.found["address"] = plc_link.node_address(
            self.device_node, list(getattr(self.online, "gateways", []) or []))
        if self.found["address"] is None:
            self.note("the device node would not say which address it points "
                      "at; logging in wherever it does")
        return None

    def nothing_to_change(self):
        """The IDE finds nothing a Keep login would apply. None if so.

        is_online_change_possible is read here, before any login: it is the
        only reason a caller is ever given for an online change that cannot
        be made, since Force's own refusal names none (research 17.2).
        """
        uptodate, problem = plc_keep.uptodate(self.application)
        possible = getattr(self.application, "is_online_change_possible",
                           None)
        self.found["uptodate"] = uptodate
        self.found["online_change_possible"] = (
            possible if isinstance(possible, bool) else None)
        if problem:
            return problem
        if uptodate:
            return None
        self.found["methods"] = ["download"] + (
            ["online_change"] if possible is True else [])
        return ("the working copy differs from what was last downloaded (the "
                "IDE's is_uptodate is false): code, IO mapping, device "
                "settings or libraries changed. A plain login would put that "
                "on the controller, so nothing was done. %s"
                % _methods_line(self.found["methods"]))

    def the_ide_agrees(self):
        """The controller holds this copy's last download (research 17.4)."""
        problem = plc_keep.the_ide_agrees(self, WATCHER_DOWNLOAD)
        if problem:
            self.found["methods"] = ["download"]
            return "%s; nothing was done" % problem
        return None

    # -- online -------------------------------------------------------------

    def hand_over(self):
        """Credentials and the dialog switch, right before an online call.

        Every call, not once: held credentials went stale across a runtime
        restart and a project reopen, and the dialog came back (17.5). The
        note is said once; it is the same every time.
        """
        note, problem = plc_link.silence_credential_dialogs(
            self.online, self.globals, self.args.get("credentials"))
        if problem:
            return problem
        if note not in self.notes:
            self.note(note)
        return None

    def connected(self, job):
        """Trip.connected, with the credentials handed over first."""
        return self.hand_over() or Trip.connected(self, job)

    def open_session(self):
        """The IDE's online application, and whether it is logged in."""
        problem = self.hand_over()
        if problem:
            return problem
        try:
            self.session = self.online.create_online_application(
                self.application)
        except Exception as exc:
            return ("the IDE would not make an online application, so "
                    "nothing was done: " + one_line(exc))
        self.found["logged_in"] = self._logged_in()
        return None

    def not_logged_in_yet(self):
        """Already logged in: nothing to do, and that is a success."""
        if self.found["logged_in"] is not True:
            return None
        self.found["state"] = state_of(self.session)
        return Done("already logged in, application %s; nothing was done"
                    % self.found["state"])

    def still_logged_in(self):
        """Not logged in: nothing to log out of, and that is a success."""
        if self.found["logged_in"] is True:
            return None
        return Done("not logged in; nothing was done")

    def log_in_keep(self):
        """Log in, applying nothing: the steps before made sure of that."""
        options = entry.borrowed(self.globals, "OnlineChangeOption")
        if options is None:
            return ("this IDE did not provide OnlineChangeOption, so a login "
                    "that neither downloads nor makes an online change cannot "
                    "be asked for explicitly; nothing was done")
        return self.log_in(options.Keep, "Keep", "nothing")

    def log_in(self, option, option_name, changed):
        """login(option), and what the summary will say it changed."""
        problem = self.hand_over()
        if problem:
            return problem
        try:
            self.session.login(option, False)
        except Exception as exc:
            return plc_link.login_refusal(one_line(exc))
        self.note("logged in with OnlineChangeOption.%s" % option_name)
        self.found["changed"] = changed
        self.expected["logged_in"] = True
        return None

    def log_out(self):
        problem = self.hand_over()
        if problem:
            return problem
        try:
            self.session.logout()
        except Exception as exc:
            return "the logout was refused: " + one_line(exc)
        self.expected["logged_in"] = False
        return None

    def read_state(self):
        """Read back what the action left: every state reported is read,
        never assumed. A session that is not logged in has no application
        to report on."""
        self.found["logged_in"] = self._logged_in()
        if self.found["logged_in"]:
            self.found["state"] = state_of(self.session)
        return None

    def _logged_in(self):
        try:
            return self.session.is_logged_in is True
        except Exception as exc:
            self.note("whether the application is logged in could not be "
                      "read: " + one_line(exc))
            return None

    # -- what came of it ----------------------------------------------------

    def verdict(self):
        """ok when everything read back as the action meant it to."""
        for key in sorted(self.expected):
            if self.found[key] != self.expected[key]:
                return self.failed(
                    "the %s returned without an error, but %s reads back %s, "
                    "not %s" % (self.action, key, self.found[key],
                                self.expected[key]))
        return self.result(True, "%s: %s" % (self.action, self.described()))

    def described(self):
        """One line of what the controller's session is now."""
        found = self.found
        parts = ["logged in" if found["logged_in"] else "logged out"]
        if found["address"]:
            parts.append("at " + found["address"])
        if found["state"]:
            parts.append("application " + found["state"])
        parts.append(CHANGED[found["changed"]])
        return ", ".join(parts)

    def reported(self):
        return dict((key, self.found[key]) for key in REPORT_KEYS)


def _methods_line(methods):
    """The --method values that would apply a change, as a sentence."""
    if "online_change" in methods:
        return ("To apply it: --method online_change -y (keeps the "
                "application running) or --method download -y (full "
                "download, leaves the application stopped).")
    return ("An online change cannot carry this change, so only --method "
            "download -y applies it (full download, leaves the application "
            "stopped).")
