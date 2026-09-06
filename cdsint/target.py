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

import time

from cds.core import commands, instances
from cds.core.exits import EXIT_FAILED, EXIT_TARGET, EXIT_TIMEOUT
from cdsint.exits import Failure
from cdsint.flags import DEFAULT_TIMEOUT_S

POLL_S = 0.05

GONE = "gone"  # the watcher shut down while we were waiting

# How long the registration has to stay missing before we believe it. Under
# IronPython the watcher has no os.replace, so its every-two-second rewrite
# deletes the file and renames the new one into place — for a moment there is
# no registration, and a single missed read would call a healthy IDE dead.
GONE_AFTER_S = 1.0


class Target(object):
    """One live watcher, resolved once and then driven."""

    def __init__(self, root, target=None, timeout=DEFAULT_TIMEOUT_S):
        self.root = root
        self.timeout = timeout
        try:
            # --timeout is how long the caller will wait, so it is also how
            # long a busy instance still counts as alive. Both places, one
            # meaning.
            self.reg = instances.resolve_target(live_instances(root, timeout),
                                                target, busy_timeout=timeout)
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

    None means it timed out; GONE means the watcher went away. A command that
    times out is un-queued, so it cannot fire later against an IDE whose owner
    has walked away. If the watcher already claimed it, the result it writes
    is swept by that watcher's next start instead.
    """
    commands.write_command(root, instance_id, cmd["command"], cmd["args"],
                           cmd_id=cmd["id"])
    deadline = time.time() + timeout
    missing_since = None
    try:
        while True:
            result = commands.take_result(root, instance_id, cmd["id"])
            if result is not None:
                return result
            if instances.read(root, instance_id) is not None:
                missing_since = None
            else:
                missing_since = missing_since or time.time()
                if time.time() - missing_since >= GONE_AFTER_S:
                    # The instance directory goes with the registration, so
                    # the answer is not coming. For `stop` that IS the answer;
                    # for anything else, better to say so than wait out the
                    # clock.
                    return GONE
            if time.time() >= deadline:
                commands.delete_command(root, instance_id, cmd["id"])
                return None
            time.sleep(poll)
    except KeyboardInterrupt:
        commands.delete_command(root, instance_id, cmd["id"])
        raise


def live_instances(root, busy_timeout=DEFAULT_TIMEOUT_S):
    return [r for r in instances.read_all(root)
            if instances.is_alive(r, busy_timeout=busy_timeout)]

