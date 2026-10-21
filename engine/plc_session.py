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
--method values that would apply the change. A login by a --method, which
does change it, adds its own steps (engine/plc_method.py).

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

# The OnlineChangeOption member --method online_change logs in with. Not
# Try, which falls back to a full download where an online change is not
# possible; Force refuses instead, but with a bare "Login failed..." that
# names no reason, so is_online_change_possible is read before it
# (docs/trace-research.md 17.2).
ONLINE_CHANGE = "Force"

# What a login that raised may have left, by what it was asked to change.
# A login asked to change nothing is plc_link.login_refusal's to word.
INTERRUPTED = {
    "download": ("the download did not complete, and the controller may now "
                 "be stopped or partly written: "),
    "online_change": ("the online change did not complete; it never falls "
                      "back to a full download. The IDE said: "),
}


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
        self.changes = "nothing"    # what the login is about to change
        self.expected = {}          # what found must read back as afterwards
        self.found.update({"logged_in": None, "state": None, "address": None,
                           "changed": "nothing", "boot_application": False,
                           "uptodate": None, "online_change_possible": None,
                           "methods": []})

    def run(self, steps):
        """Every step inside one nested script run; then the answer."""
        answer = ide_private.in_script_run(
            entry.borrowed(self.globals, "online"),
            lambda: self._through(steps))
        if isinstance(answer, Done):
            return self.result(True, "%s: %s" % (self.action, answer.summary))
        if answer:
            return self.failed(answer)
        return self.verdict()

    def _through(self, steps):
        """The steps' answer. A failure once there is a session still
        reports what the session is: one after the login is logged in."""
        answer = first_problem(steps)
        if answer and not isinstance(answer, Done) and \
                self.session is not None:
            self.read_state()
        return answer

    # -- before any online call ---------------------------------------------

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
        problem = self.read_the_change()
        if problem:
            return problem
        if self.found["uptodate"]:
            return None
        self.found["methods"] = ["download"] + (
            ["online_change"] if self.found["online_change_possible"]
            else [])
        return ("the working copy differs from what was last downloaded (the "
                "IDE's is_uptodate is false): code, IO mapping, device "
                "settings or libraries changed. A plain login would put that "
                "on the controller, so nothing was done. %s"
                % _methods_line(self.found["methods"]))

    def read_the_change(self):
        """is_uptodate and is_online_change_possible into found, both read
        offline. None, or why is_uptodate cannot be trusted."""
        uptodate, problem = plc_keep.uptodate(self.application)
        possible = getattr(self.application, "is_online_change_possible",
                           None)
        self.found["uptodate"] = uptodate
        self.found["online_change_possible"] = (
            possible if isinstance(possible, bool) else None)
        return problem

    def the_ide_agrees(self):
        """The controller holds this copy's last download (research 17.4)."""
        problem = self.connected(self._holds_this_download)
        if problem:
            return "%s; nothing was done" % problem
        return None

    def _holds_this_download(self):
        """The judgement, with data.methods set only for a controller found
        holding another program or none: one that did not answer, or whose
        file would not come, may hold exactly this one."""
        header, unread = plc_keep.fetched(self)
        if unread:
            return self._why_unread(unread)
        return self._needs_a_download(
            plc_keep.judgement(self, header, WATCHER_DOWNLOAD))

    def _why_unread(self, unread):
        """A fetch that failed: a download is the cure only when the
        controller's own listing shows no application there."""
        parent, name = self.remote["dir"].rsplit("/", 1)
        try:
            absent = name not in plc_link.names_in(self.device, parent)
        except Exception as exc:
            self.note("%s could not be listed either: %s"
                      % (parent, one_line(exc)))
            absent = False
        if not absent:
            return unread
        return self._needs_a_download(
            "%s, and the controller holds no application %s; %s"
            % (unread, name, WATCHER_DOWNLOAD))

    def _needs_a_download(self, problem):
        if problem:
            self.found["methods"] = ["download"]
        return problem

    # -- online -------------------------------------------------------------

    def hand_over(self):
        """Credentials and the dialog switch, right before an online call."""
        return plc_link.hand_over_for(self)

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

    def log_in_with(self, option_name):
        """login() with the OnlineChangeOption member of that name, asked
        for by name so that no IDE default decides what it applies. What
        it changes is self.changes, which the steps before it settled."""
        options = entry.borrowed(self.globals, "OnlineChangeOption")
        if options is None:
            return ("this IDE did not provide OnlineChangeOption, so a login "
                    "with OnlineChangeOption.%s cannot be asked for; nothing "
                    "was done" % option_name)
        problem = self.hand_over()
        if problem:
            return problem
        try:
            # delete_foreign_apps False, as the --project download has it.
            self.session.login(getattr(options, option_name), False)
        except Exception as exc:
            return self._refused(one_line(exc))
        self.note("logged in with OnlineChangeOption.%s" % option_name)
        self.found["changed"] = self.changes
        self.expected["logged_in"] = True
        return None

    def _refused(self, said):
        """What a login that raised `said` may have left on the controller.
        Another client holding it refused before anything was sent."""
        interrupted = INTERRUPTED.get(self.changes)
        if interrupted is None or plc_link.ALREADY_LOGGED_IN in said.lower():
            return plc_link.login_refusal(said)
        return interrupted + said

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
