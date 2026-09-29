# -*- coding: utf-8 -*-
"""Which IDEs are running a watcher, and which one did the caller mean.

Each watcher keeps a registration file beside its instance directory and
rewrites it every couple of seconds. The heartbeat says the watcher is
answering; it cannot say an IDE is gone while that IDE is busy, because a
busy watcher cannot beat. The CLI can also ask whether the pid still runs
(cdsint/process.py) and hands the answer in here as pid_alive: a function
from a registration to True, False, or None for "cannot tell". The IDE side
has no such function, so everything here also works without one.

Timestamps are stored twice: an ISO string for whoever opens the file, and an
epoch number for the arithmetic here. Deriving one from the other would mean
parsing local time, and local time has an hour a year where that is ambiguous.

Pure Python (PRINCIPLES.md 4): no CODESYS imports.
"""
from __future__ import print_function

import ntpath
import os
import shutil

from cds.core import commands, ipc

STATE_IDLE = "idle"
STATE_BUSY = "busy"

# Starting points, not settled numbers (docs/WATCHER.md 2.1).
HEARTBEAT_INTERVAL_S = 2.0
ALIVE_TIMEOUT_S = 10.0
BUSY_TIMEOUT_S = 120.0
STALE_TIMEOUT_S = 60.0
# Busy for longer than this, and a starting watcher takes the IDE for one
# that crashed mid-command. The IDE side cannot ask whether a pid runs, so
# this is its only way to clear such a record; it has to be long enough that
# no real command gets near it.
ABANDONED_AFTER_S = 6 * 3600.0


# --------------------------------------------------------------------------
# The record
# --------------------------------------------------------------------------

def new_registration(instance_id, pid, ide, project_path,
                     sync_dir=None, watcher_version=None, now=None):
    """Build the registration record for a watcher that just started.

    started_at_epoch is what lets a reader tell this IDE from a later
    process that was handed the same pid (cdsint/process.py).
    """
    now = ipc.now(now)
    reg = {
        "instance_id": instance_id,
        "pid": pid,
        "ide": ide,
        "sync_dir": sync_dir,
        "started_at": ipc.iso(now),
        "started_at_epoch": now,
        "watcher_version": watcher_version,
    }
    set_project(reg, project_path)
    set_state(reg, STATE_IDLE, now)
    return stamp_heartbeat(reg, now)


def set_project(reg, project_path):
    """Record which project the IDE has open; it can change without a restart."""
    reg["project_path"] = project_path
    # ntpath: the path came from the IDE, so it is a Windows path even when
    # whoever reads this registration is not on Windows.
    reg["project_name"] = ntpath.splitext(ntpath.basename(project_path or ""))[0]
    return reg


def stamp_heartbeat(reg, now=None):
    """Mark the watcher as still running. Both fields, same instant."""
    now = ipc.now(now)
    reg["heartbeat"] = ipc.iso(now)
    reg["heartbeat_epoch"] = now
    return reg


def set_state(reg, state, now=None, command=None):
    """Switch between idle and busy, recording when a busy stretch began
    and on what, so a caller who cannot wait that long is told why."""
    now = ipc.now(now)
    busy = state == STATE_BUSY
    reg["state"] = state
    reg["busy_since"] = ipc.iso(now) if busy else None
    reg["busy_since_epoch"] = now if busy else None
    reg["busy_command"] = command if busy else None
    return reg


def is_alive(reg, now=None, idle_timeout=ALIVE_TIMEOUT_S,
             busy_timeout=BUSY_TIMEOUT_S, pid_alive=None):
    """Is this instance still there?

    An idle watcher must have beaten recently. A busy one cannot beat at all
    while a command holds the main thread, so it is trusted for as long as the
    caller is willing to wait for that command -- unless its process is gone,
    which is what an IDE that crashed mid-command leaves behind.
    """
    now = ipc.now(now)
    if process_gone(reg, pid_alive):
        return False
    if reg.get("state") == STATE_BUSY:
        started = reg.get("busy_since_epoch")
        return started is not None and (now - float(started)) <= busy_timeout
    beat = reg.get("heartbeat_epoch")
    return beat is not None and (now - float(beat)) <= idle_timeout


def process_gone(reg, pid_alive=None):
    """Only a definite no counts: None is "cannot tell", not "dead"."""
    return pid_alive is not None and pid_alive(reg) is False


def stopped_answering(reg, now=None, pid_alive=None, working=False):
    """Has the watcher a caller is waiting on gone, though its file is there?

    The waiting side's question, not is_alive's: the caller already picked
    this instance, and busy for longer than it will wait is its own timeout
    to call. What is left is a process that is gone, and an idle watcher
    that stopped beating -- unless a command of its is running (working),
    which is what an idle record with a stopped heartbeat also looks like
    when the busy write was lost (docs/WATCHER.md 5).
    """
    if process_gone(reg, pid_alive):
        return True
    if reg.get("state") == STATE_BUSY or working:
        return False
    return not is_alive(reg, now)


# --------------------------------------------------------------------------
# The files
# --------------------------------------------------------------------------

def write(root, reg):
    ipc.write_json(ipc.registration_path(root, reg["instance_id"]), reg)


def read(root, instance_id):
    return ipc.read_json(ipc.registration_path(root, instance_id))


def read_all(root):
    """Every registration under root, alive or not, sorted by instance id.

    A .json without an instance_id is not a registration, whoever put it
    there, and everything downstream indexes that field.
    """
    out = []
    for name in ipc.json_names(root):
        reg = ipc.read_json(os.path.join(root, name))
        if isinstance(reg, dict) and reg.get("instance_id"):
            out.append(reg)
    return out


def delete(root, instance_id):
    """Drop an instance: its registration file and its whole directory."""
    ipc.remove_file(ipc.registration_path(root, instance_id))
    shutil.rmtree(ipc.instance_dir(root, instance_id), ignore_errors=True)


def prune_stale(root, now=None, max_age=STALE_TIMEOUT_S,
                abandoned_after=ABANDONED_AFTER_S):
    """Delete registrations left behind by watchers that died.

    Runs inside the IDE, where nothing can ask whether a pid still runs, so
    the only evidence is time. A busy instance is running a command and
    cannot beat while it does; a real import on a real project takes
    minutes, and deleting its directory pulls cmd/ and result/ out from
    under a live process. So busy is spared for abandoned_after, which no
    real command comes near, and only then taken for an IDE that crashed.

    The state field is not enough on its own. On Windows the watcher's
    rewrite to busy can fail while a CLI has the file open, and then the
    record says idle, with a heartbeat that stops for as long as the command
    runs. The command's .running file is the evidence that does not depend
    on that write (cds/core/commands.py), and it gets the same allowance.

    Tying this to the command timeout (the CLI's 120 seconds) looked like
    protection but only covered commands shorter than that, which is not the
    interesting case. Cleaning up after a dead watcher and deciding a command
    has taken too long are different jobs; they do not get to share a number.

    Returns the instance ids that were removed.
    """
    now = ipc.now(now)
    removed = []
    for reg in read_all(root):
        if _recent(reg, now, max_age, abandoned_after):
            continue
        claimed = commands.running_since(root, reg["instance_id"])
        if claimed is not None and now - claimed <= abandoned_after:
            continue
        delete(root, reg["instance_id"])
        removed.append(reg["instance_id"])
    return removed


def _recent(reg, now, max_age, abandoned_after):
    """Has this instance shown a sign of life recently enough to be spared?"""
    if reg.get("state") == STATE_BUSY:
        since, allowed = reg.get("busy_since_epoch"), abandoned_after
    else:
        since, allowed = reg.get("heartbeat_epoch"), max_age
    return now - float(since or 0.0) <= allowed


# --------------------------------------------------------------------------
# Picking one
# --------------------------------------------------------------------------

class TargetError(Exception):
    """No single instance matched. matches is empty, or holds the candidates."""

    def __init__(self, message, matches=None):
        Exception.__init__(self, message)
        self.matches = list(matches or [])


def resolve_target(regs, target=None, now=None, busy_timeout=BUSY_TIMEOUT_S,
                   pid_alive=None):
    """Pick the one live instance the caller meant.

    An exact instance id wins. Otherwise target is read as a project name
    (case-insensitive); with no target at all, a lone live instance is it.
    Anything else raises TargetError so the caller can list the candidates.
    """
    now = ipc.now(now)
    alive = [r for r in regs if is_alive(r, now, busy_timeout=busy_timeout,
                                         pid_alive=pid_alive)]
    matches = _meant(alive, target)
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise TargetError("several live IDEs match; pass --target", matches)
    raise TargetError(_why_none(regs, target, now, busy_timeout, pid_alive))


def _meant(regs, target):
    """The ones target names: its exact id, else its project name."""
    if not target:
        return regs
    exact = [r for r in regs if r.get("instance_id") == target]
    return exact or [r for r in regs
                     if (r.get("project_name") or "").lower() == target.lower()]


def _why_none(regs, target, now, busy_timeout, pid_alive):
    """Nothing live matched. Busy for longer than the caller waits is not
    the same thing as not there, and saying "no live IDE" sent people
    looking for an IDE that was open in front of them."""
    busy = [r for r in _meant(regs, target)
            if r.get("state") == STATE_BUSY and not process_gone(r, pid_alive)]
    if not busy:
        return ("no live IDE matches %r" % (target,) if target
                else "no live IDE found")
    return "; ".join(
        "%s has been busy for %ds running %s, longer than the %gs this "
        "caller waits (--timeout)" % (
            r["instance_id"], now - float(r.get("busy_since_epoch") or now),
            r.get("busy_command") or "a command", busy_timeout)
        for r in busy)
