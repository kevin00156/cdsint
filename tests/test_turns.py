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


# --- the change count ------------------------------------------------------

def cmd_of(command, **args):
    return commands.new_command(command, args,
                                caller={"pid": 7, "cwd": r"C:\wt\b"})


def test_a_changing_command_moves_the_count_and_a_read_does_not():
    count = turns.ChangeCount("s")
    count.took(cmd_of("compare"))
    assert count.token() == "s.0"
    count.took(cmd_of("import", yes=True))
    assert count.token() == "s.1"


def test_a_matching_after_runs_and_a_moved_one_is_refused_by_name():
    count = turns.ChangeCount("s")
    assert count.stale(cmd_of("plc download", after="s.0")) is None
    count.took(cmd_of("import", yes=True))
    said = count.stale(cmd_of("plc download", after="s.0"))
    assert "s.0" in said and "s.1" in said
    assert "import" in said and "pid 7" in said


def test_a_count_from_an_earlier_watcher_is_refused():
    said = turns.ChangeCount("new").stale(cmd_of("plc download",
                                                 after="old.0"))
    assert "started again" in said


def test_a_command_without_after_is_never_refused_by_the_count():
    count = turns.ChangeCount("s")
    count.took(cmd_of("import", yes=True))
    assert count.stale(cmd_of("plc download")) is None


def test_another_project_opened_moves_the_count():
    count = turns.ChangeCount("s")
    count.opened(r"C:\p\other.project")
    assert count.token() == "s.1" and "other.project" in count.last["command"]


def step(command, changes):
    result = commands.new_result(commands.new_command(command), True)
    result["changes"] = changes
    return result


def test_a_run_whose_steps_count_one_after_another_has_no_seam():
    assert turns.seams([step("import", "s.4"), step("export", "s.5"),
                        step("compare", "s.5"), step("build", "s.6")]) == []


def test_a_jump_between_two_steps_names_them():
    found = turns.seams([step("import", "s.4"), step("export", "s.6")])
    assert len(found) == 1 and "between import and export" in found[0]


def test_records_without_a_count_say_nothing():
    assert turns.seams([step("import", None), step("export", None)]) == []


def test_the_watcher_counts_what_it_runs_and_answers_with_the_count(
        watch, monkeypatch):
    watch.handlers["build"] = lambda cmd, started: commands.new_result(
        cmd, True)
    answering(watch, monkeypatch)
    runner = target.Target(watch.root)
    first, = runner.run([("build", {})])
    second, = runner.run([("build", {})])
    assert first["changes"] == watch.changed.session + ".1"
    assert second["changes"] == watch.changed.session + ".2"


def test_the_watcher_refuses_a_command_whose_after_is_stale(watch,
                                                            monkeypatch):
    ran = []
    watch.handlers["build"] = lambda cmd, started: (
        ran.append(1) or commands.new_result(cmd, True))
    answering(watch, monkeypatch)
    runner = target.Target(watch.root)
    runner.run([("build", {})])
    refused, = runner.run([("build", {"after": watch.changed.session
                                       + ".0"})])
    assert not refused["ok"] and "change count" in refused["error"]
    # Refused before its body: nothing ran, and nothing was counted.
    assert ran == [1] and watch.changed.count == 1


def stub_round_trip(watch, between=None):
    def body(cmd, started):
        if between is not None and cmd["command"] == "compare":
            between()
        return commands.new_result(cmd, True, data={})
    for name in ("import", "export", "compare", "build"):
        watch.handlers[name] = body


def test_verify_says_the_count_a_download_hands_back(watch, monkeypatch,
                                                     capsys):
    stub_round_trip(watch)
    answering(watch, monkeypatch)
    assert cli.main(["verify", "-y"]) == EXIT_OK
    token = watch.changed.token()
    assert "--after %s" % token in capsys.readouterr().out


def test_verify_fails_when_another_caller_changed_the_ide_between_its_steps(
        watch, monkeypatch, capsys):
    # Somebody's import, landing in the gap before compare was queued.
    stub_round_trip(watch, between=lambda: watch.changed.took(
        cmd_of("import", yes=True)))
    answering(watch, monkeypatch)
    assert cli.main(["verify", "-y"]) != EXIT_OK
    assert "changed by another caller" in capsys.readouterr().err
