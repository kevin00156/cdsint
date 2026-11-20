# -*- coding: utf-8 -*-
"""Whose turn a watcher is: a command that changes something is refused, not
queued, while anybody else's command is there.

Several agents can drive one IDE. Its queue runs their commands one at a
time, but one at a time is not enough: an import queued behind another
agent's import runs on a project that agent has just changed, and whoever
queued it is told nothing (owner decision, 2026-11-20). A command that only
reads still queues; it can only ever be late, not wrong.

The check has to hold between CLIs that cannot see each other, and the one
thing they share is the command directory. So a caller queues first and
looks second, and if any command but its own is there, queued or running,
it takes its own back and is refused. Of two callers, the one that queued
second looks after the first was already there, so neither can find the
directory empty while the other's command runs. Two that queue at the same
moment can see each other and both be refused; that costs a retry, never a
project.

The other half is the change count below, for what the turn cannot see:
another caller's command between two of yours.

Pure Python (PRINCIPLES.md 4): no CODESYS imports.
"""
from __future__ import print_function

import errno
import os
import random

from cds.core import commands, ipc

# What changes nothing in the IDE, on the controller or in the sync folder.
# stop is the watcher's own, and a caller ending a watcher is not taking a
# turn on its project. Everything not named here is refused while it would
# have to wait.
READS_ONLY = frozenset(["ping", "status", "stop", "compare", "discover",
                        "trace list", "trace job", "trace save"])

QUEUED = "queued"
RUNNING = "running"
_SUFFIX = {QUEUED: ".json", RUNNING: commands.RUNNING}


def changes(command, args=None):
    """Does this command take a turn? plc trace --stop does not: it ends
    the recording that holds the turn, so refusing it would leave the
    recording nothing to end it."""
    if command in READS_ONLY:
        return False
    return not (command == "plc trace" and (args or {}).get("stop"))


def caller():
    """Who is asking, for whoever is refused while this command runs."""
    return {"pid": os.getpid(), "cwd": os.getcwd()}


def others(root, instance_id, own_ids):
    """Every changing command in the instance's directory that is not one of
    own_ids, oldest first, as (cmd_id, QUEUED or RUNNING).

    A read waiting its turn is not one: it changes nothing a change could
    be run on top of, and counting it let somebody's compare, queued in the
    gap between two of a verify's steps, fail that verify (bench,
    2026-11-20). A file that will not read is counted, since what it holds
    cannot be told; the cost is a retry."""
    directory = ipc.command_dir(root, instance_id)
    return [(cmd_id, state) for cmd_id, state in _all(directory, own_ids)
            if _changing(os.path.join(directory, cmd_id + _SUFFIX[state]))]



def _changing(path):
    held = _read(path)
    return held is None or changes(held.get("command"), held.get("args"))


def _all(directory, own_ids):
    try:
        names = os.listdir(directory)
    except (IOError, OSError) as exc:
        if getattr(exc, "errno", None) == errno.ENOENT:
            return []
        raise
    found = []
    for name in sorted(names):
        for state, suffix in sorted(_SUFFIX.items()):
            cmd_id = name[:-len(suffix)]
            if name.endswith(suffix) and cmd_id not in own_ids:
                found.append((cmd_id, state))
    return found


def refusal(root, instance_id, command, cmd_id, state):
    """The sentence a refused caller is given: what holds the turn, since
    when, and who asked for it."""
    path = os.path.join(ipc.command_dir(root, instance_id),
                        cmd_id + _SUFFIX[state])
    held = _read(path) or {}
    who = held.get("caller") or {}
    by = (" by pid %s in %s" % (who.get("pid"), who.get("cwd"))
          if who else "")
    doing = ("is running %s" if state == RUNNING else "has %s queued") % (
        held.get("command") or "a command")
    return ("%s did not run: %s %s (%s since %s%s), and a command that "
            "changes something is refused rather than queued while another "
            "is there. Nothing was done; run it again once that one is "
            "finished (cdsint list shows the state)"
            % (command, instance_id, doing, state, _since(path, held), by))


def _read(path):
    try:
        return ipc.read_json(path)
    except (EnvironmentError, ValueError):
        return None     # gone, or mid-rewrite: the sentence goes without


def _since(path, held):
    """When it was claimed for a running one (the mark is touched then), when
    it was queued otherwise."""
    if path.endswith(commands.RUNNING):
        try:
            return ipc.iso(os.path.getmtime(path))
        except EnvironmentError:
            pass
    return held.get("created_at") or "a moment ago"


# --------------------------------------------------------------------------
# The change count
# --------------------------------------------------------------------------

class ChangeCount(object):
    """How many changing commands one watcher has run, as a token a caller
    can hand back: "<session>.<count>".

    The turn above keeps two commands from running at once; it cannot keep
    another caller's import from landing between somebody's verify and that
    somebody's download, which are two commands. The sync folder is one per
    project and every caller of this watcher shares it, so comparing the IDE
    with the disk cannot tell whose content the IDE holds either. What can
    is a count of what was done to it: verify hands back the token after its
    last step, plc download --after hands it back, and the watcher refuses
    the download if anything has been run since (owner decision,
    2026-11-20). The session is new with every watcher, so a token outlives
    neither a restart nor, since a project opened by hand is counted as a
    change, the project it was taken on.

    Every changing command counts once the watcher hands it to its body,
    whether it then worked or not: an import that failed halfway has
    changed the project as much as one that worked. Nothing done by hand in
    the IDE is counted, but opening another project.
    """

    def __init__(self, session=None):
        self.session = session or "%08x" % random.getrandbits(32)
        self.count = 0
        self.last = None    # what made the last change: command, at, caller

    def token(self):
        return "%s.%d" % (self.session, self.count)

    def took(self, cmd, now=None):
        """The watcher is about to run cmd."""
        if changes(cmd.get("command"), cmd.get("args")):
            self._changed(cmd.get("command"), cmd.get("caller"), now)

    def opened(self, path, now=None):
        """The IDE has another project open than it had."""
        self._changed("opening %s" % (path or "no project"), None, now)

    def _changed(self, what, caller, now):
        self.count += 1
        self.last = {"command": what, "at": ipc.iso(ipc.now(now)),
                     "caller": caller}

    def stale(self, cmd):
        """Why cmd may not run, when its --after is not this token, or None."""
        after = (cmd.get("args") or {}).get("after")
        if after is None or after == self.token():
            return None
        if _session(after) != self.session:
            why = ("that count was taken from another run of this watcher, "
                   "which has been started again since")
        else:
            why = ("%d change(s) have been made since, the last %s"
                   % (self.count - _count(after), _described(self.last)))
        return ("%s did not run: it was asked to act on the IDE as it was at "
                "change count %s, and it is at %s now: %s. Nothing was done; "
                "run verify again and pass the count it reports"
                % (cmd.get("command"), after, self.token(), why))


def _described(last):
    who = (last or {}).get("caller") or {}
    by = " by pid %s in %s" % (who.get("pid"), who.get("cwd")) if who else ""
    return "%s at %s%s" % (last["command"], last["at"], by)


def _session(token):
    return token.rsplit(".", 1)[0]


def _count(token):
    return int(token.rsplit(".", 1)[1])


def seams(results):
    """Where another caller changed the IDE between two steps of one run, as
    sentences. Each step's count is the one before it, plus one if the step
    changes something; a jump means somebody else's command ran in the gap
    the turn cannot cover. Records without a count (the --project form) say
    nothing, and nor does a step that failed: it may have been refused
    before its body, uncounted, and the run stops at it anyway."""
    found = []
    counted = [r for r in results if r.get("changes") and r["ok"]]
    for before, after in zip(counted, counted[1:]):
        expected = "%s.%d" % (_session(before["changes"]),
                              _count(before["changes"])
                              + int(changes(after["command"])))
        if after["changes"] != expected:
            found.append("the IDE was changed by another caller between %s "
                         "and %s: the change count went from %s to %s"
                         % (before["command"], after["command"],
                            before["changes"], after["changes"]))
    return found
