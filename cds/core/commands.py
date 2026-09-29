# -*- coding: utf-8 -*-
"""The drop box: the CLI leaves a command, the watcher leaves a result.

A command file name is "<13-digit millisecond stamp>-<6 hex>.json", so plain
alphabetical order is oldest-first and two commands issued in the same
millisecond still get separate files. The watcher takes one at a time by
renaming it to "<id>.running" before it runs it, writes the result under the
same id, then removes the .running file. That file is the one sign on disk
that a command is in progress which does not depend on the registration being
rewritten -- and on Windows that rewrite can fail (docs/WATCHER.md 2.1).

The CLI deletes each result once it has read it. Results nobody came back for
(the CLI was killed, say) are swept by the watcher on its next start.

Pure Python (PRINCIPLES.md 4): no CODESYS imports.
"""
from __future__ import print_function

import errno
import os
import random

from cds.core import ipc
from cds.core.text import as_text

RESULT_TTL_S = 3600.0


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def new_id(now=None, suffix=None):
    """Make "<13-digit ms>-<6 hex>": sorts by age, unique within a millisecond."""
    if suffix is None:
        suffix = "%06x" % random.randint(0, 0xFFFFFF)
    return "%013d-%s" % (int(ipc.now(now) * 1000), suffix)


def new_command(command, args=None, now=None, cmd_id=None, deadline=None):
    """The record that says what to run, whether or not it is ever a file.

    A headless run never queues anything — one process runs the whole list —
    but the result it writes is the same record the watcher writes, and that
    record is built from this one. So both callers start here, and neither
    can end up with a command record the other's readers cannot read.

    deadline_epoch is when the caller stops waiting; None means it waits
    for as long as it takes, which is what a headless run does.
    """
    now = ipc.now(now)
    return {
        "id": cmd_id or new_id(now),
        "command": command,
        "args": dict(args or {}),
        "created_at": ipc.iso(now),
        "deadline_epoch": deadline,
    }


def write_command(root, instance_id, command, args=None, now=None, cmd_id=None,
                  deadline=None):
    """Queue one command for an instance. Returns the record as written."""
    cmd = new_command(command, args, now, cmd_id, deadline)
    ipc.write_json(_command_path(root, instance_id, cmd["id"]), cmd)
    return cmd


def overdue(cmd, now=None):
    """Has the caller who queued this stopped waiting for it?

    A CLI that times out takes its command back out of the queue, but one
    that is killed cannot, and its command would then run whenever the
    watcher got to it -- an import an hour later, against a project its
    owner has been editing since. Nobody is left to read that answer.
    """
    deadline = cmd.get("deadline_epoch")
    return deadline is not None and ipc.now(now) > float(deadline)


def list_command_ids(root, instance_id):
    """Queued command ids, oldest first (the file name sorts that way)."""
    names = ipc.json_names(ipc.command_dir(root, instance_id))
    return [n[:-len(".json")] for n in names]


def next_command(root, instance_id):
    """The oldest queued command, or None if the queue is empty.

    A file that is not a command is set aside as <name>.bad, not raised.
    It keeps its place at the head of the queue, so raising would fail every
    tick on the same file, block every command queued behind it, and stop
    the heartbeat that tells the CLI this IDE is alive.
    """
    for cmd_id in list_command_ids(root, instance_id):
        path = _command_path(root, instance_id, cmd_id)
        try:
            cmd = ipc.read_json(path)
        except ValueError as exc:
            _set_aside(path, exc)
            continue
        if isinstance(cmd, dict) and "id" in cmd:
            return cmd
        if cmd is not None:
            _set_aside(path, "not a command object")
    return None


def _set_aside(path, why):
    print("watcher: %s is not a command (%s); set aside as .bad"
          % (os.path.basename(path), why))
    os.rename(path, path + ".bad")


def delete_command(root, instance_id, cmd_id):
    ipc.remove_file(_command_path(root, instance_id, cmd_id))


RUNNING = ".running"


def claim_command(root, instance_id, cmd_id):
    """Take a command off the queue, leaving the mark that it is running.

    A rename, so there is no moment with neither file. Touched afterwards:
    the file's age has to be how long the command has run, not how long
    ago the CLI queued it.

    False when the command is no longer there: its caller timed out and
    took it back between our reading it and claiming it, and a command
    nobody is waiting for is not run.
    """
    path = _running_path(root, instance_id, cmd_id)
    try:
        os.rename(_command_path(root, instance_id, cmd_id), path)
    except (IOError, OSError) as exc:
        if getattr(exc, "errno", None) == errno.ENOENT:
            return False
        raise
    os.utime(path, None)
    return True


def release_command(root, instance_id, cmd_id):
    ipc.remove_file(_running_path(root, instance_id, cmd_id))


def running_since(root, instance_id):
    """When the command in progress was claimed, or None if none is.

    The oldest, should there be several: a watcher that died mid-command
    leaves its mark behind, and that one is the one that says how long.
    """
    directory = ipc.command_dir(root, instance_id)
    try:
        names = os.listdir(directory)
    except (IOError, OSError):
        return None
    stamps = []
    for name in names:
        if name.endswith(RUNNING):
            try:
                stamps.append(os.path.getmtime(os.path.join(directory, name)))
            except (IOError, OSError):
                continue    # released between the listing and the look
    return min(stamps) if stamps else None


def _running_path(root, instance_id, cmd_id):
    return os.path.join(ipc.command_dir(root, instance_id), cmd_id + RUNNING)


def _command_path(root, instance_id, cmd_id):
    return os.path.join(ipc.command_dir(root, instance_id), cmd_id + ".json")


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------

def new_result(cmd, ok, error=None, messages=None, needs_input=None,
               stdout_tail=None, started_at=None, finished_at=None, data=None,
               denied=None):
    """Build the result record for a finished command.

    started_at and finished_at are epoch seconds. A failed result must carry
    an error text, so "it failed and I don't know why" cannot be written
    (PRINCIPLES.md 6). needs_input names the argument that would have answered
    a dialog the script tried to pop. data is whatever this particular command
    has to hand back — status returns the live instance record there.

    denied says the project's own policy refused the command, and it is a
    field of its own rather than a phrase inside error for the same reason
    needs_input is: the caller decides what to do from it (SPEC 4.3 gives it
    exit 5), and matching on wording is not a decision, it is a guess.
    """
    if not ok and not error:
        raise ValueError("a failed result must carry an error message")
    started = ipc.now(started_at)
    finished = ipc.now(finished_at)
    return {
        "id": cmd["id"],
        "ok": bool(ok),
        "command": cmd.get("command"),
        "started_at": ipc.iso(started),
        "finished_at": ipc.iso(finished),
        "elapsed_s": round(finished - started, 3),
        "messages": list(messages or []),
        "stdout_tail": stdout_tail or "",
        "error": error,
        "needs_input": needs_input,
        "denied": denied,
        "data": data,
    }


def message(level, text):
    """One line of what a command had to say, as a result record carries it.

    Two producers write these — the stand-in UI recording a dialog nobody saw,
    and the watcher's own notes — and a reader of `messages` cannot tell which
    made a given line, so they had better be the same shape. The text is
    converted here because what the stand-in UI is handed is whatever the IDE
    passed to a dialog, which need not be text yet.
    """
    return {"level": level, "text": as_text(text)}


def write_result(root, instance_id, result):
    ipc.write_json(_result_path(root, instance_id, result["id"]), result)


def read_result(root, instance_id, cmd_id):
    return ipc.read_json(_result_path(root, instance_id, cmd_id))


def take_result(root, instance_id, cmd_id):
    """Read a result and delete it. None if it is not there yet."""
    result = read_result(root, instance_id, cmd_id)
    if result is not None:
        ipc.remove_file(_result_path(root, instance_id, cmd_id))
    return result


def prune_results(root, instance_id, now=None, max_age=RESULT_TTL_S):
    """Delete results nobody came back for. Returns the ids removed."""
    now = ipc.now(now)
    directory = ipc.result_dir(root, instance_id)
    removed = []
    for name in ipc.json_names(directory):
        path = os.path.join(directory, name)
        try:
            age = now - os.path.getmtime(path)
        except (IOError, OSError):
            # The CLI deletes a result the moment it reads one, so a name
            # listed a microsecond ago can already be gone. Not our business.
            continue
        if age <= max_age:
            continue
        ipc.remove_file(path)
        removed.append(name[:-len(".json")])
    return removed


def _result_path(root, instance_id, cmd_id):
    return os.path.join(ipc.result_dir(root, instance_id), cmd_id + ".json")
