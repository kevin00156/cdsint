# -*- coding: utf-8 -*-
"""What one IDE's watcher does on each tick: claim a command, answer it, beat.

Nothing here starts or stops a watcher — cds/ide/session.py does that, and it
does it by arming a timer and letting the script end, because a script that
keeps running holds the main thread and leaves the IDE unclickable
(docs/WATCHER.md 6). Keeping that half out of this file is what lets this
half be tested under CPython.

Ticks land on the UI thread, so object-model calls from them are legal and no
cross-thread machinery is needed. No threads, no time.sleep(), no
execute_on_primary_thread (SP21 removed it).

A command is claimed by renaming its file out of the queue *before* running
it. The plan had the delete last, but a watcher that dies mid-import would
then find the same import queued again on restart. A lost result costs the
caller a timeout; a repeated import costs it a project.
"""
from __future__ import print_function

import os
import traceback

from cds.core import commands, instances, ipc, turns
from cds.ide import display, entries, messages, project, silent
from cds.ide.beat import KeepsItsRecord
from cds.ide.recording import TRACE, WHILE_RECORDING, HoldsARecording


class Watcher(KeepsItsRecord, HoldsARecording):
    """One IDE's listener: on every tick, claim a command, answer it, beat."""

    def __init__(self, ide_globals, root=None, version=None):
        if "system" not in ide_globals:
            # TypeError, not KeyError: the argument is wrong, and a KeyError
            # from a constructor reads as a lookup that went wrong inside it.
            raise TypeError("the watcher needs the IDE's globals, and this "
                            "mapping has no `system` in it")
        self.ide = ide_globals
        self.root = root or ipc.default_root()
        self.running = True
        self.busy = False
        self.timer = None
        now = ipc.now()
        path = self._open_project_path()
        self.reg = instances.new_registration(
            ipc.make_instance_id(path, os.getpid()), os.getpid(),
            project.ide_name(), path, watcher_version=version, now=now)
        self.instance_id = self.reg["instance_id"]
        self.started_epoch = now
        self.doing = None       # the command running right now, for the display
        self.done = 0
        self.last = None        # {"command", "ok", "elapsed"} of the last one
        self.display_to = None  # set by session when there is a window to feed
        self.form = None        # the window itself, so session can close it
        self._last_beat = 0.0
        self._deferring = False
        self.changed = turns.ChangeCount()
        self.handlers = {
            "ping": self._ping,
            "status": self._status,
            "stop": self._stop,
        }
        for name in entries.COMMANDS:
            self.handlers[name] = self._run_script
        for name in entries.WATCHER_REFUSES:
            self.handlers[name] = self._refuse

    # -- lifecycle ---------------------------------------------------------

    def start(self):
        """Claim an instance directory and announce we are listening."""
        instances.prune_stale(self.root)
        self._refuse_to_double_book()
        ipc.ensure_dirs(self.root, self.instance_id)
        commands.prune_results(self.root, self.instance_id)
        self._beat(ipc.now())
        messages.note(self.ide, "cdsint: listening as " + self.instance_id)
        print("watcher: listening as " + self.instance_id)
        print("watcher: " + ipc.instance_dir(self.root, self.instance_id))

    def _refuse_to_double_book(self):
        """Two watchers in one IDE would fight over the same directory."""
        existing = instances.read(self.root, self.instance_id)
        if existing is not None and instances.is_alive(existing):
            raise RuntimeError(
                "a watcher is already listening as %s (started %s) — stop it "
                "before starting another" % (self.instance_id,
                                             existing.get("started_at")))

    def tick(self):
        """One turn: take a command if there is one, answer it, beat.

        Never raises — an exception escaping a WinForms handler becomes a
        thread-exception dialog that can take the IDE down. Returns whether a
        turn actually happened.
        """
        if not self.running or self.busy or silent.running():
            # Not running: the teardown belongs to whoever armed us. Busy: a
            # command is pumping messages of its own and the timer fired
            # again on top of it. silent.running(): some other caller has a
            # script going — this one is belt-and-braces, self.busy already
            # covers our own commands.
            return False
        self.busy = True
        try:
            self._poll_recording()
            commands.clear_running(self.root, self.instance_id, self._held())
            cmd = commands.next_command(self.root, self.instance_id)
            if cmd is not None:
                self.run_one(cmd)
            self.beat_if_due()
            self._show()
        except BaseException:
            print("watcher: tick failed\n" + traceback.format_exc())
        finally:
            self.busy = False
        return True

    def shutdown(self):
        """Leave nothing behind for the next watcher to trip over.

        A recording is finished first: no tick will come again, so its
        caller is answered now, with what was recorded so far, and the
        answer is left behind for that caller to collect.
        """
        answered = self.recording is not None
        if answered:
            self._conclude(self.recording,
                           self.recording.finish("the watcher was stopped"))
        try:
            instances.delete(self.root, self.instance_id,
                             keep_results=answered)
        except EnvironmentError as exc:
            # A CLI reading the file right now holds it open. Leaving the
            # registration behind is survivable — the next watcher's
            # prune_stale clears it — and raising here would bury whatever
            # actually stopped the loop.
            print("watcher: could not clear %s (%s)" % (self.instance_id, exc))
        messages.note(self.ide, "cdsint: stopped " + self.instance_id)
        print("watcher: stopped " + self.instance_id)

    # -- one command -------------------------------------------------------

    def run_one(self, cmd):
        """Claim, run, and answer a single command. Never raises.

        Answering is inside the try as well: writing the result can hit the
        same Windows sharing violation as the heartbeat (WATCHER.md 2.1),
        and an instance left stuck in `busy` is worse than a lost answer. Once
        busy_since goes stale the CLI stops seeing the instance, while
        prune_stale keeps sparing it because it is busy, for hours.

        A command its caller took back before we could claim it is not run
        and not answered: nobody is waiting for either.

        A plc trace comes back as an entries.Pending: it is held, still
        claimed, and answered by a later tick (_poll_recording).
        """
        started = ipc.now()
        if not self._claim(cmd):
            return None
        result = None
        try:
            self._beat(started, instances.STATE_BUSY, cmd.get("command"))
            self.doing = cmd.get("command")
            # Paint BUSY before the work starts: the IDE stops repainting for
            # the whole of an export, so afterwards is too late to say so.
            self._show()
            messages.note(self.ide, "cdsint: %s started" % self.doing)
            result = self._answer(cmd, started)
            if isinstance(result, entries.Pending):
                self._hold(result)
                return result
            self._write(result)
        except Exception:
            print("watcher: answering %s failed\n%s"
                  % (cmd.get("id"), traceback.format_exc()))
        finally:
            if not isinstance(result, entries.Pending):
                self._close(cmd, result, started)
        return result

    def _write(self, result):
        result["changes"] = self.changed.token()
        commands.write_result(self.root, self.instance_id, result)
        # A caller that gave up before we answered leaves its result
        # behind. Sweeping here keeps the directory bounded on a watcher
        # that runs for days; what we just wrote is far too young to catch.
        commands.prune_results(self.root, self.instance_id)

    def _close(self, cmd, result, started):
        """The end of one command, answered or not: say so, beat, unmark."""
        self._finished(cmd, result, started)
        self._beat(ipc.now(), self._rest_state())
        self._release(cmd)
        self._show()

    def _claim(self, cmd):
        """Take the command off the queue. False: do not run it."""
        try:
            claimed = commands.claim_command(self.root, self.instance_id,
                                             cmd["id"])
        except EnvironmentError:
            print("watcher: could not claim %s\n%s"
                  % (cmd.get("id"), traceback.format_exc()))
            return False
        return claimed and self._scrubbed(cmd)

    def _scrubbed(self, cmd):
        """Keep the device password off disk once the command is claimed.

        If the rewrite fails the file still holds it, so the command does not
        run: the file is removed and the caller is told, rather than left to
        wait out its timeout; the reason goes with it, since it names a copy
        that would not delete (scrub_running). False: do not run it.
        """
        try:
            commands.scrub_running(self.root, self.instance_id, cmd)
            return True
        except EnvironmentError as exc:
            print("watcher: could not scrub %s\n%s"
                  % (cmd.get("id"), traceback.format_exc()))
            why = exc
        self._release(cmd)
        try:
            self._write(commands.new_result(
                cmd, False, error="the watcher could not remove the device "
                                  "login from the command file, so it did "
                                  "not run the command: %s" % (why,)))
        except EnvironmentError:
            print("watcher: could not answer %s" % cmd.get("id"))
        return False

    def _release(self, cmd):
        """Take the running mark away. Left behind, it only delays pruning."""
        try:
            commands.release_command(self.root, self.instance_id, cmd["id"])
        except EnvironmentError as exc:
            print("watcher: could not clear the mark of %s (%s)"
                  % (cmd.get("id"), exc))

    def _finished(self, cmd, result, started):
        """Remember how that one went, for the status window and the log."""
        self.doing = None
        self.done += 1
        ok = bool(result and result.get("ok"))
        self.last = {"command": cmd.get("command"), "ok": ok,
                     "elapsed": ipc.now() - started}
        messages.note(self.ide, "cdsint: %s %s in %.1fs"
                      % (cmd.get("command"), "ok" if ok else "FAILED",
                         self.last["elapsed"]),
                      ok=ok)

    def _show(self):
        """Push the current picture at whatever is displaying it.

        A window that throws is a cosmetic problem; it must not be able to
        stop the watcher answering commands.
        """
        if self.display_to is None:
            return
        try:
            self.display_to(display.describe(self))
        except Exception:
            print("watcher: status window failed\n" + traceback.format_exc())

    def _answer(self, cmd, started):
        """Turn one command into a result record, whatever it takes.

        The script commands answer for themselves (cds/ide/entries.py), so
        this is the net under the rest: a handler that raises still has to
        leave the caller a record to read rather than a wait that times out.
        """
        try:
            return self._dispatch(cmd, started)
        except Exception:
            return commands.new_result(cmd, False, started_at=started,
                                       error=traceback.format_exc())

    def _dispatch(self, cmd, started):
        if commands.overdue(cmd, started):
            return commands.new_result(
                cmd, False, started_at=started,
                error="the caller stopped waiting at %s; not run"
                      % ipc.iso(float(cmd["deadline_epoch"])))
        name = cmd.get("command")
        if name == TRACE and (cmd.get("args") or {}).get("stop"):
            return self._stop_the_recording(cmd, started)
        if self.recording is not None and name not in WHILE_RECORDING:
            return commands.new_result(cmd, False, started_at=started,
                                       error=self._recording_until())
        stale = self.changed.stale(cmd)
        if stale is not None:
            return commands.new_result(cmd, False, started_at=started,
                                       error=stale)
        handler = self.handlers.get(cmd.get("command"))
        if handler is None:
            known = ", ".join(sorted(self.handlers))
            return commands.new_result(
                cmd, False, started_at=started,
                error="unknown command %r; this watcher knows %s"
                      % (cmd.get("command"), known))
        self.changed.took(cmd)
        return handler(cmd, started)

    # -- the commands ------------------------------------------------------

    def _ping(self, cmd, started):
        note = commands.message("info", "pong from " + self.instance_id)
        return commands.new_result(cmd, True, started_at=started,
                                   messages=[note])

    def _status(self, cmd, started):
        """Hand back the instance record. The heartbeat keeps it current."""
        live = dict(self.reg)
        # Answering this is what makes us busy, so reporting "busy" would say
        # nothing. Report the state we go back to; `list` shows the live one.
        instances.set_state(live, self._rest_state(), started)
        note = commands.message("info", live["project_path"]
                                or "no project open")
        return commands.new_result(cmd, True, started_at=started, data=live,
                                   messages=[note])

    def _stop(self, cmd, started):
        self.running = False
        note = commands.message("info", "stopping " + self.instance_id)
        return commands.new_result(cmd, True, started_at=started,
                                   messages=[note])

    def _refuse(self, cmd, started):
        """A command this watcher knows and will not run (entries.py).

        Answered rather than dropped: "unknown command" would send the
        reader looking for a typo, when what they need is the reason and
        the other form.
        """
        return commands.new_result(
            cmd, False, started_at=started,
            error=entries.WATCHER_REFUSES[cmd["command"]])

    def _run_script(self, cmd, started):
        """Press the button on one of the commands in cds/ide/entries.py."""
        return entries.answer(self.ide, cmd, started)
