# -*- coding: utf-8 -*-
"""The watcher's registration: which project it has open, and its heartbeat.

A mixin of cds/ide/watcher.py's Watcher, moved out of it unchanged when the
change count joined it there and the file ran past PRINCIPLES 2's limit; it
is the one part of the watcher that writes the registration.
"""
from __future__ import print_function

from cds.core import instances, ipc
from cds.ide import project

BEAT_ATTEMPTS = 5


class KeepsItsRecord(object):
    """The registration and the beat. Needs Watcher's ide, root and reg."""

    def _open_project_path(self):
        return project.path_of(self.ide.get("projects"))

    def _refresh_project(self):
        """Follow the project the IDE has open now, not the one it had at start.

        Closing a project and opening another does not restart the watcher,
        and `list` is how a caller picks its target, so a stale name here
        means it picks the wrong IDE or none at all. instance_id keeps its
        birth name — that one is a directory.
        """
        instances.set_project(self.reg, self._open_project_path())
        self.reg["sync_dir"] = project.sync_dir(self.ide.get("projects"))

    def beat_if_due(self, now=None):
        """Write the heartbeat, but only every HEARTBEAT_INTERVAL_S."""
        now = ipc.now(now)
        if now - self._last_beat < instances.HEARTBEAT_INTERVAL_S:
            return False
        return self._beat(now)

    def _beat(self, now, state=None, command=None):
        """Write the heartbeat, or shrug and let the next turn try again.

        On Windows the registration cannot be replaced while a CLI has it open
        for reading. A CLI holds it for the length of one read, so the write
        is tried again at once, a few times, before it is given up -- no
        sleep, there is none on this thread (SPEC D5). It matters most for
        the beat that says busy: the next turn is after the command, and
        without it the record says idle while the heartbeat stops for the
        whole of a long import. Past that, a missed beat is not worth ending
        a watcher over. _last_beat is left alone so the retry happens on the
        next turn rather than in two seconds.
        """
        if state is not None:
            instances.set_state(self.reg, state, now, command)
        self._refresh_project()
        instances.stamp_heartbeat(self.reg, now)
        failure = None
        for _attempt in range(BEAT_ATTEMPTS):
            try:
                instances.write(self.root, self.reg)
            except EnvironmentError as exc:
                failure = exc
                continue
            self._deferring = False
            self._last_beat = now
            return True
        if not self._deferring:  # once per episode, not once per turn
            print("watcher: heartbeat deferred (%s)" % failure)
            self._deferring = True
        return False
