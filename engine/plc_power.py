# -*- coding: utf-8 -*-
"""plc run and plc stop: start or stop the application through the login the
watcher's IDE holds (design 2026-10-21-watcher-online, 5.5).

Neither logs in. A login that was not asked for would be a second way to
change what a controller does, and the one that can is `plc login --method`.
So a session that is not logged in is a refusal that points there, and the
steps are the session's own plus one: start or stop, then the state read
back. A call that returns without an error is not a state; the application
is asked what it is in (engine/plc_session.py's verdict compares).
"""
from __future__ import print_function

from engine.plc_download import state_of
from engine.plc_session import Done, SessionTrip
from engine.plc_trip import RUNNING, one_line

STOPPED = "stop"

# The state each action leaves (what the verdict expects), mapped to the
# session method that gets it there: run calls start(), stop calls stop().
CALLS = {RUNNING: "start", STOPPED: "stop"}


class PowerTrip(SessionTrip):
    """One plc run or plc stop."""

    def __init__(self, action, args, ide_globals):
        SessionTrip.__init__(self, action, args, ide_globals)
        self.wanted = RUNNING if action == "run" else STOPPED

    def logged_in_first(self):
        if self.found["logged_in"] is True:
            return None
        return ("the application is not logged in, so it cannot be %s; log "
                "in first (plc login), nothing was done"
                % ("started" if self.wanted == RUNNING else "stopped"))

    def already(self):
        """Already in the asked state: nothing to do, and that is a success."""
        self.found["state"] = state_of(self.session)
        if self.found["state"] != self.wanted:
            return None
        return Done("application already %s; nothing was done" % self.wanted)

    def switch(self):
        problem = self.hand_over()
        if problem:
            return problem
        try:
            getattr(self.session, CALLS[self.wanted])()
        except Exception as exc:
            return "the application would not %s: %s" % (
                CALLS[self.wanted], one_line(exc))
        self.expected["state"] = self.wanted
        return None
