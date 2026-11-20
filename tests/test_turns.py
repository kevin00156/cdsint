# -*- coding: utf-8 -*-
"""Tests for cds/core/turns.py and the CLI's use of it: a changing command is
refused, not queued, while another caller's command is there."""
import os
import time

import pytest

from cds.core import commands, ipc, turns
from cds.core.exits import EXIT_BUSY, EXIT_OK
from cds.ide import watcher
from cdsint import cli, process, target
from tests.fakes import make_globals


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv(ipc.ROOT_ENV, str(tmp_path))
    monkeypatch.setattr(process, "running", lambda pid, not_after=None:
                        True if pid == os.getpid() else None)
    return str(tmp_path)


@pytest.fixture
def watch(root):
    started = watcher.Watcher(make_globals(), root)
    started.start()
    return started


def answering(watch, monkeypatch):
    def tick(_seconds):
        cmd = commands.next_command(watch.root, watch.instance_id)
        if cmd is not None:
            watch.run_one(cmd)
    monkeypatch.setattr(time, "sleep", tick)


def somebody_queued(watch, command="import", claimed=False):
    cmd = commands.write_command(watch.root, watch.instance_id, command,
                                 {"yes": True},
                                 caller={"pid": 4242, "cwd": r"C:\wt\other"})
    if claimed:
        commands.claim_command(watch.root, watch.instance_id, cmd["id"])
    return cmd


def queued(watch):
    return commands.list_command_ids(watch.root, watch.instance_id)


# --- which commands take a turn ------------------------------------------

@pytest.mark.parametrize("command", ["import", "build", "export",
                                     "plc download", "plc login",
                                     "trace apply", "plc trace"])
def test_a_command_that_changes_something_takes_a_turn(command):
    assert turns.changes(command, {})


@pytest.mark.parametrize("command", ["ping", "status", "compare", "discover",
                                     "trace list"])
def test_a_command_that_only_reads_does_not(command):
    assert not turns.changes(command, {})


def test_trace_stop_does_not_take_the_turn_the_recording_holds():
    assert not turns.changes("plc trace", {"stop": True})


# --- refused, not queued ---------------------------------------------------

def test_a_change_is_refused_while_another_command_runs(watch, capsys):
    other = somebody_queued(watch, claimed=True)
    assert cli.main(["build"]) == EXIT_BUSY
    said = capsys.readouterr().err
    assert "is running import" in said and "pid 4242" in said
    assert r"C:\wt\other" in said
    # Taken back: it must not run after the other one, on what that one left.
    assert queued(watch) == []
    assert os.path.exists(os.path.join(
        ipc.command_dir(watch.root, watch.instance_id),
        other["id"] + commands.RUNNING))


def test_a_change_is_refused_while_another_waits_its_turn(watch, capsys):
    other = somebody_queued(watch)
    assert cli.main(["build"]) == EXIT_BUSY
    assert "has import queued" in capsys.readouterr().err
    assert queued(watch) == [other["id"]]


def test_a_read_still_queues_behind_another_command(watch, monkeypatch):
    somebody_queued(watch, command="ping")
    answering(watch, monkeypatch)
    assert cli.main(["ping"]) == EXIT_OK


def test_an_empty_queue_runs_the_change(watch, monkeypatch):
    seen = []
    watch.handlers["build"] = lambda cmd, started: (
        seen.append(cmd["caller"]) or commands.new_result(cmd, True))
    answering(watch, monkeypatch)
    assert cli.main(["build"]) == EXIT_OK
    assert seen == [{"pid": os.getpid(), "cwd": os.getcwd()}]


def test_of_two_that_queue_at_once_only_one_is_left_to_run(watch):
    # The first to look sees the other and takes its own back; the second
    # then finds nobody. Had both looked first, both would be refused: a
    # retry is the price, and neither ever runs on top of the other.
    mine = somebody_queued(watch)
    theirs = somebody_queued(watch)
    with pytest.raises(target.Failure) as refused:
        target.my_turn(watch.root, watch.instance_id, mine, set([mine["id"]]))
    assert refused.value.code == EXIT_BUSY
    target.my_turn(watch.root, watch.instance_id, theirs,
                   set([theirs["id"]]))
    assert queued(watch) == [theirs["id"]]


def test_one_the_watcher_claimed_first_is_waited_for_not_refused(watch):
    mine = somebody_queued(watch, claimed=True)
    somebody_queued(watch)
    # No exception: it is already running, and only its result says how.
    target.my_turn(watch.root, watch.instance_id, mine, set([mine["id"]]))


def test_a_mark_of_this_callers_previous_step_does_not_refuse_the_next(
        watch, monkeypatch):
    # The watcher answers, then removes the running mark; verify's next step
    # can be queued in between.
    runner = target.Target(watch.root)
    left = []

    def leave_the_mark(cmd, started):
        left.append(cmd["id"])
        return commands.new_result(cmd, True)

    real_release = commands.release_command
    monkeypatch.setattr(commands, "release_command",
                        lambda root, iid, cmd_id: None if cmd_id in left
                        else real_release(root, iid, cmd_id))
    watch.handlers["import"] = leave_the_mark
    watch.handlers["export"] = leave_the_mark
    answering(watch, monkeypatch)
    results = runner.run([("import", {"yes": True}), ("export", {})])
    assert [r["ok"] for r in results] == [True, True]


# --- the watcher's side ----------------------------------------------------

def test_the_watcher_clears_a_mark_it_failed_to_remove(watch):
    # Left there it would refuse every change for as long as the watcher runs.
    somebody_queued(watch, command="ping", claimed=True)
    watch.tick()
    assert turns.others(watch.root, watch.instance_id, set()) == []


def test_the_watcher_keeps_the_mark_of_the_recording_it_holds(watch):
    held = somebody_queued(watch, command="plc trace", claimed=True)

    class Held(object):
        cmd = held
        until = None

        def poll(self):
            return None

    watch.recording = Held()
    watch.tick()
    assert turns.others(watch.root, watch.instance_id, set()) == [
        (held["id"], turns.RUNNING)]
