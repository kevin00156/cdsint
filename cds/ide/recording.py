# -*- coding: utf-8 -*-
"""A plc trace the watcher holds between its ticks, and what it answers meanwhile.

In the watcher a plc trace's body returns once the trace has started, and
the recording goes on (engine/plc_trace_watch.py): the watcher's timer may
not wait (SPEC D5). What comes back is an entries.Pending, which the
watcher keeps here, polls once a tick, and answers the caller with when it
is done. A mixin of cds/ide/watcher.py's Watcher, kept apart because it is
the one part of the watcher that spans ticks, and together they ran past
PRINCIPLES 2's limit.
"""
from __future__ import print_function

import traceback

from cds.core import commands, instances, ipc

# The one command that can go on after its body returns, and what is still
# answered while it does. The watcher's own stop is not among them: closing
# the watcher from the IDE finishes a recording (shutdown), but a stop sent
# by a caller is refused so that --stop stays the one way to end it early.
TRACE = "plc trace"
WHILE_RECORDING = ("ping", "status")


class HoldsARecording(object):
    """The watcher's recording, if it has one. Needs Watcher's _beat, _show,
    _write and _close."""

    recording = None    # the entries.Pending of a plc trace recording

    def _poll_recording(self):
        """One look at the recording; its caller is answered once it is done."""
        if self.recording is None:
            return
        result = self.recording.poll()
        if result is not None:
            self._conclude(self.recording, result)

    def _hold(self, pending):
        """Keep a recording between ticks. Its command stays claimed, so the
        caller waiting on it is not taken for abandoned (cdsint/target.py
        Watching), and the registration says recording rather than busy, so
        a --stop sent later still finds this watcher alive."""
        self.recording = pending
        self.doing = None
        self._beat(ipc.now(), instances.STATE_RECORDING,
                   pending.cmd.get("command"))
        self._show()

    def _conclude(self, pending, result):
        """Answer a recording's caller, and go back to taking commands."""
        self.recording = None
        try:
            self._write(result)
        except Exception:
            print("watcher: answering %s failed\n%s"
                  % (pending.cmd.get("id"), traceback.format_exc()))
        self._close(pending.cmd, result, pending.started)

    def _rest_state(self):
        return (instances.STATE_RECORDING if self.recording is not None
                else instances.STATE_IDLE)

    def _stop_the_recording(self, cmd, started):
        """plc trace --stop: answered here; the engine is not pressed."""
        if self.recording is None:
            return commands.new_result(
                cmd, False, started_at=started,
                error="nothing is recording in this IDE, so there is nothing "
                      "to stop")
        self.recording.stop("plc trace --stop")
        note = commands.message("info", "the recording ends on the next "
                                "tick; the plc trace that started it reports")
        return commands.new_result(cmd, True, started_at=started,
                                   messages=[note])

    def _recording_until(self):
        """The refusal for anything but --stop, ping and status meanwhile."""
        until = self.recording.until
        when = (" until about %s" % ipc.iso(until).split("T")[-1]
                if until else "")
        return ("a plc trace is recording in this IDE%s. Until it ends this "
                "watcher answers only plc trace --stop, ping and status"
                % when)
