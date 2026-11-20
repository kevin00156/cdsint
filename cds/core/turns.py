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

Pure Python (PRINCIPLES.md 4): no CODESYS imports.
"""
from __future__ import print_function

import errno
import os

from cds.core import commands, ipc

# What changes nothing in the IDE, on the controller or in the sync folder.
# stop is the watcher's own, and a caller ending a watcher is not taking a
# turn on its project. Everything not named here is refused while it would
# have to wait.
READS_ONLY = frozenset(["ping", "status", "stop", "compare", "discover",
                        "trace list", "trace job", "trace save"])

QUEUED = "queued"
RUNNING = "running"


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
    """Every command in the instance's directory that is not one of own_ids,
    oldest first, as (cmd_id, QUEUED or RUNNING)."""
    try:
        names = os.listdir(ipc.command_dir(root, instance_id))
    except (IOError, OSError) as exc:
        if getattr(exc, "errno", None) == errno.ENOENT:
            return []
        raise
    found = []
    for name in sorted(names):
        for suffix, state in ((".json", QUEUED), (commands.RUNNING, RUNNING)):
            cmd_id = name[:-len(suffix)]
            if name.endswith(suffix) and cmd_id not in own_ids:
                found.append((cmd_id, state))
    return found


def refusal(root, instance_id, command, cmd_id, state):
    """The sentence a refused caller is given: what holds the turn, since
    when, and who asked for it."""
    path = os.path.join(ipc.command_dir(root, instance_id),
                        cmd_id + (".json" if state == QUEUED
                                  else commands.RUNNING))
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
