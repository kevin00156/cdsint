# -*- coding: utf-8 -*-
"""The `--target` form: a watcher inside an IDE somebody already has open.

Writes a command file, waits for the result file, hands it back. Nothing here
touches CODESYS — the whole exchange is files in the instance directory
(docs/WATCHER.md), which is what lets the CLI be plain CPython.

The other form is cdsint/headless.py. Both answer `run(steps)`, which is
what lets `verify` be written once (SPEC D2). Only the headless one has
`sync_dir()`: naming the folder a run took for the truth is a --project
thing, because the --target form is talking to an IDE somebody set up and
has open (SPEC 4.2, cdsint/cli.py show_folder).
"""
from __future__ import print_function

import os
import time

from cds.core import commands, instances, ipc
from cds.core.exits import EXIT_FAILED, EXIT_TARGET, EXIT_TIMEOUT
from cdsint import process
from cdsint.exits import Failure
from cdsint.flags import DEFAULT_TIMEOUT_S

POLL_S = 0.05

GONE = "gone"  # the watcher shut down while we were waiting

# How long the registration has to stay missing before we believe it. Under
# IronPython the watcher has no os.replace, so its every-two-second rewrite
# deletes the file and renames the new one into place — for a moment there is
# no registration, and a single missed read would call a healthy IDE dead.
GONE_AFTER_S = 1.0


def _resolve(root, target, timeout):
    """resolve_target, with the same debounce the wait has.

    Every registration goes in, not the live ones: resolve_target decides
    what "live" means and it needs the timeout to say so. --timeout is how
    long the caller will wait, so it is also how long a busy instance still
    counts as alive.

    A registration between its delete and its rename (docs/WATCHER.md 2.1)
    is not there to be read, and on Windows one being deleted cannot be
    opened; either used to answer "no live IDE" for an IDE that was fine.
    Its .json.tmp is there for exactly that moment, so that is what earns
    another look, for up to GONE_AFTER_S.
    """
    give_up = time.time() + GONE_AFTER_S
    while True:
        try:
            return instances.resolve_target(
                instances.read_all(root), target, busy_timeout=timeout,
                pid_alive=process.registration_running)
        except (instances.TargetError, EnvironmentError) as exc:
            if time.time() >= give_up or not _mid_rewrite(root, exc):
                raise
        time.sleep(POLL_S)


def _mid_rewrite(root, exc):
    """Could a registration be missing only because it is being rewritten?"""
    if getattr(exc, "matches", None):
        return False    # found several: a blink never adds one
    if isinstance(exc, EnvironmentError):
        return True
    try:
        return any(n.endswith(".json.tmp") for n in os.listdir(root))
    except EnvironmentError:
        return False


class Target(object):
    """One live watcher, resolved once and then driven."""

    def __init__(self, root, target=None, timeout=DEFAULT_TIMEOUT_S):
        self.root = root
        self.timeout = timeout
        try:
            self.reg = _resolve(root, target, timeout)
        except instances.TargetError as exc:
            raise Failure(str(exc), EXIT_TARGET,
                          ["%-28s %s" % (r["instance_id"],
                                         r.get("project_path") or "(no project)")
                           for r in exc.matches])
        self.instance_id = self.reg["instance_id"]

    def describe(self):
        return self.instance_id

    def run(self, steps):
        """Run each command in turn, stopping at the first one that fails."""
        results = []
        for command, args in steps:
            results.append(self.run_one(command, args))
            if not results[-1]["ok"]:
                break
        return results

    def run_one(self, command, args):
        cmd = commands.new_command(command, args)
        result = send(self.root, self.instance_id, cmd, self.timeout)
        if result is GONE:
            return self._gone(cmd)
        if result is None:
            raise Failure("timed out after %gs waiting for %s"
                          % (self.timeout, self.instance_id), EXIT_TIMEOUT)
        return result

    def _gone(self, cmd):
        """The watcher vanished mid-wait: what that means depends on the ask.

        stop tears down one tick after answering, so the answer can be gone by
        the time we look. The instance being gone IS the confirmation, and it
        is written as the record every other answer is written as, so a reader
        of `messages` or `elapsed_s` does not have to know which of the two
        this was.
        """
        if cmd["command"] != "stop":
            raise Failure("%s stopped before answering %s"
                          % (self.instance_id, cmd["command"]), EXIT_FAILED)
        return commands.new_result(cmd, True, messages=[
            commands.message("info", "%s is gone" % self.instance_id)])


def send(root, instance_id, cmd, timeout, poll=POLL_S):
    """Queue a command and wait for its result.

    None means it timed out; GONE means the watcher went away. Either way the
    command is un-queued, so it cannot fire later against an IDE whose owner
    has walked away. If the watcher already claimed it, the result it writes
    is swept by that watcher's next start instead. The deadline travels with
    the command for the case un-queueing cannot cover: this process killed
    outright, with the command still in the queue.
    """
    deadline = time.time() + timeout
    commands.write_command(root, instance_id, cmd["command"], cmd["args"],
                           cmd_id=cmd["id"], deadline=deadline)
    watching = Watching(root, instance_id)
    try:
        while True:
            result = commands.take_result(root, instance_id, cmd["id"])
            if result is not None:
                return result
            answer = GONE if watching.gone(time.time()) else None
            if answer is GONE or time.time() >= deadline:
                commands.delete_command(root, instance_id, cmd["id"])
                return answer
            time.sleep(poll)
    except KeyboardInterrupt:
        commands.delete_command(root, instance_id, cmd["id"])
        raise


class Watching(object):
    """Is the watcher we are waiting on still there? Asked once per poll.

    Cheap every time, a real read now and then. Opening the registration
    every poll held it open often enough that the watcher's rewrite, which
    Windows refuses while anyone has the file open, failed -- and the one it
    lost was the one saying busy (docs/WATCHER.md 5). So each poll only asks
    whether the file is there, and reads it about as often as it is written.

    Missing is debounced. Under IronPython the watcher has no os.replace, so
    its rewrite deletes the registration and renames the new one into place
    -- for a moment there is no file, and one missed look would call a
    healthy IDE dead (docs/WATCHER.md 2.1). The instance directory goes with
    the registration, so once it has really stayed away the answer is not
    coming: for `stop` that IS the answer, and for anything else saying so
    beats waiting out the clock.

    Present is not proof either: an IDE that died leaves its file behind,
    and waiting on it used to cost the caller the whole --timeout. The read
    asks instances.stopped_answering, with the pid check in.
    """

    def __init__(self, root, instance_id):
        self.root = root
        self.instance_id = instance_id
        self.missing_since = None
        self.next_read = 0.0

    def gone(self, now):
        if not os.path.exists(ipc.registration_path(self.root,
                                                    self.instance_id)):
            if self.missing_since is None:
                self.missing_since = now
            return now - self.missing_since >= GONE_AFTER_S
        self.missing_since = None
        if now < self.next_read:
            return False
        self.next_read = now + instances.HEARTBEAT_INTERVAL_S
        return self._stopped_answering(now)

    def _stopped_answering(self, now):
        try:
            reg = instances.read(self.root, self.instance_id)
        except EnvironmentError:
            return False    # caught mid-rewrite on Windows; the next read
        if reg is None:
            return False    # the same, one step later; the debounce has it
        working = commands.running_since(self.root, self.instance_id)
        return instances.stopped_answering(
            reg, now, process.registration_running, working is not None)


def live_instances(root, busy_timeout=DEFAULT_TIMEOUT_S):
    return [r for r in instances.read_all(root)
            if instances.is_alive(r, busy_timeout=busy_timeout,
                                  pid_alive=process.registration_running)]

