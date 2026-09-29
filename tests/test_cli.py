# -*- coding: utf-8 -*-
"""Tests for cdsint/cli.py.

The CLI and the watcher are driven against each other in one process: the
CLI's wait is made to answer itself by running the real watcher's run_one, so
these cover the whole round trip minus the IDE.
"""
import json
import os
import time

import pytest

from cds.core import commands, instances, ipc
from cds.core.exits import (EXIT_FAILED, EXIT_OK, EXIT_TARGET,
                            EXIT_TIMEOUT)
from cds.ide import watcher
from cdsint import cli, flags, process, target
from tests.fakes import make_globals


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv(ipc.ROOT_ENV, str(tmp_path))
    # The registrations these tests make up carry pids like 9, which may or
    # may not be running on the machine the tests run on. Only this process
    # is known to be there; the tests about a dead one say so themselves.
    monkeypatch.setattr(process, "running", lambda pid, not_after=None:
                        True if pid == os.getpid() else None)
    return str(tmp_path)


@pytest.fixture
def watch(root):
    started = watcher.Watcher(make_globals(), root)
    started.start()
    return started


def answering(watch, monkeypatch):
    """Make the CLI's wait tick the watcher instead of sleeping."""
    def tick(_seconds):
        cmd = commands.next_command(watch.root, watch.instance_id)
        if cmd is not None:
            watch.run_one(cmd)
    monkeypatch.setattr(time, "sleep", tick)


# --- list ------------------------------------------------------------------

def test_list_says_so_when_nothing_is_listening(root, capsys):
    assert cli.main(["list"]) == EXIT_OK
    assert "no IDE is listening" in capsys.readouterr().out


def test_list_shows_a_live_watcher(watch, capsys):
    assert cli.main(["list"]) == EXIT_OK
    out = capsys.readouterr().out
    assert watch.instance_id in out and "softplc.project" in out


def test_list_hides_a_watcher_that_stopped_beating(root, capsys):
    instances.write(root, instances.new_registration(
        "ghost-1", 9, "old", "C:\\p\\ghost.project", now=ipc.now() - 600.0))
    cli.main(["list"])
    assert "ghost-1" not in capsys.readouterr().out


def test_list_json_is_machine_readable(watch, capsys):
    cli.main(["list", "--json"])
    regs = json.loads(capsys.readouterr().out)
    assert regs[0]["instance_id"] == watch.instance_id


# --- picking a target ------------------------------------------------------

def test_a_command_with_no_live_ide_exits_two(root, capsys):
    assert cli.main(["ping"]) == EXIT_TARGET
    assert "no live IDE" in capsys.readouterr().err


def test_an_ambiguous_target_exits_two_and_lists_the_candidates(root, capsys):
    for pid in (11, 22):
        instances.write(root, instances.new_registration(
            "softplc-%d" % pid, pid, "ide", "C:\\p\\softplc.project"))
    assert cli.main(["ping", "--target", "softplc"]) == EXIT_TARGET
    err = capsys.readouterr().err
    assert "softplc-11" in err and "softplc-22" in err


def test_a_project_name_finds_the_watcher(watch, monkeypatch):
    answering(watch, monkeypatch)
    assert cli.main(["ping", "--target", "softplc"]) == EXIT_OK


# --- the round trip --------------------------------------------------------

def test_ping_comes_back(watch, monkeypatch, capsys):
    answering(watch, monkeypatch)
    assert cli.main(["ping"]) == EXIT_OK
    assert "pong" in capsys.readouterr().out


def test_the_target_form_does_not_name_a_sync_folder(watch, monkeypatch,
                                                     capsys):
    # SPEC 4.2 puts that line in the --project section, where the caller may
    # not know which folder the run will read. Here the folder belongs to an
    # IDE somebody set up and has open, and a line that suddenly appeared in
    # front of `ping` would break anything reading the first one.
    answering(watch, monkeypatch)
    cli.main(["ping"])
    assert not capsys.readouterr().out.startswith("sync folder:")


def test_status_prints_what_the_ide_has_open(watch, monkeypatch, capsys):
    answering(watch, monkeypatch)
    assert cli.main(["status"]) == EXIT_OK
    assert "softplc" in capsys.readouterr().out


def test_stop_ends_the_watcher(watch, monkeypatch):
    answering(watch, monkeypatch)
    assert cli.main(["stop"]) == EXIT_OK
    assert watch.running is False


def test_json_prints_the_whole_result(watch, monkeypatch, capsys):
    answering(watch, monkeypatch)
    cli.main(["status", "--json"])
    result = json.loads(capsys.readouterr().out)
    assert result["command"] == "status" and result["ok"] is True


def test_a_failed_command_exits_one(watch, monkeypatch, capsys):
    watch.handlers["ping"] = lambda cmd, started: commands.new_result(
        cmd, False, error="the IDE said no", started_at=started)
    answering(watch, monkeypatch)
    assert cli.main(["ping"]) == EXIT_FAILED
    assert "the IDE said no" in capsys.readouterr().err


def test_the_reason_is_not_printed_twice(watch, monkeypatch, capsys):
    # error is usually just the first bad message wearing another hat.
    watch.handlers["ping"] = lambda cmd, started: commands.new_result(
        cmd, False, error="no project open", started_at=started,
        messages=[{"level": "error", "text": "no project open"}])
    answering(watch, monkeypatch)
    cli.main(["ping"])
    printed = capsys.readouterr()
    assert (printed.out + printed.err).count("no project open") == 1


def test_a_failure_shows_what_the_script_printed(watch, monkeypatch, capsys):
    watch.handlers["ping"] = lambda cmd, started: commands.new_result(
        cmd, False, error="it broke", started_at=started,
        stdout_tail="the last thing the IDE said")
    answering(watch, monkeypatch)
    cli.main(["ping"])
    assert "the last thing the IDE said" in capsys.readouterr().err


def test_a_command_that_needs_an_answer_exits_one(watch, monkeypatch, capsys):
    # The watcher sets error to the question itself (silent.Outcome), so the
    # CLI must not print that long text twice.
    watch.handlers["ping"] = lambda cmd, started: commands.new_result(
        cmd, False, error="Confirm Import?", started_at=started,
        needs_input={"question": "Confirm Import?", "arg": "yes"})
    answering(watch, monkeypatch)
    assert cli.main(["ping"]) == EXIT_FAILED
    printed = capsys.readouterr()
    assert "--yes" in printed.err
    assert (printed.out + printed.err).count("Confirm Import?") == 1


def test_a_question_with_no_flag_behind_it_does_not_invent_one(watch,
                                                               monkeypatch,
                                                               capsys):
    # The sync-folder setup has no flag in the --target form; the question
    # itself says which file to write instead.
    question = "no sync folder; write Line.cdsint.json beside the project"
    watch.handlers["ping"] = lambda cmd, started: commands.new_result(
        cmd, False, error=question, started_at=started,
        needs_input={"question": question, "arg": None})
    answering(watch, monkeypatch)
    assert cli.main(["ping"]) == EXIT_FAILED
    assert "--None" not in capsys.readouterr().err


# --- the flags the four real commands take ---------------------------------

def parse(argv):
    return flags.command_args(flags.build_parser().parse_args(argv))


def test_export_passes_the_orphan_choice():
    assert parse(["export", "--delete-orphans"]) == {"delete_orphans": True}


def test_a_flag_left_out_arrives_as_not_said():
    # None, not False: the watcher has to tell "leave them" from "did not say".
    assert parse(["export"]) == {"delete_orphans": None}


def test_import_carries_yes():
    assert parse(["import", "--yes"]) == {"yes": True}


def test_import_without_yes_leaves_the_watcher_to_ask():
    assert parse(["import"]) == {"yes": None}


def test_build_carries_the_application_name():
    assert parse(["build", "--app", "App_2"]) == {"app": "App_2"}


def test_compare_takes_no_arguments_of_its_own():
    assert parse(["compare"]) == {}


def test_the_arguments_reach_the_watcher(watch, monkeypatch):
    seen = {}

    def record(cmd, started):
        seen.update(cmd["args"])
        return commands.new_result(cmd, True, started_at=started)

    watch.handlers["export"] = record
    answering(watch, monkeypatch)
    cli.main(["export", "--delete-orphans"])
    assert seen == {"delete_orphans": True}


# --- giving up -------------------------------------------------------------

def test_a_silent_watcher_times_out_with_exit_three(watch, capsys):
    assert cli.main(["ping", "--timeout", "0"]) == EXIT_TIMEOUT
    assert "timed out" in capsys.readouterr().err


def test_a_timed_out_command_is_taken_off_the_queue(watch):
    # Otherwise it fires later, at an IDE whose owner has walked away.
    cli.main(["ping", "--timeout", "0"])
    assert commands.list_command_ids(watch.root, watch.instance_id) == []


def test_the_queued_command_says_when_the_caller_stops_waiting(watch,
                                                                monkeypatch):
    # Un-queueing on a timeout does not help when this process is killed;
    # the deadline in the file is what stops the watcher running it later.
    seen = []

    def look(_seconds):
        seen.append(commands.next_command(watch.root, watch.instance_id))
        watch.run_one(seen[-1])
    monkeypatch.setattr(time, "sleep", look)
    before = time.time()
    assert cli.main(["ping", "--timeout", "30"]) == EXIT_OK
    assert before + 30 <= seen[0]["deadline_epoch"] <= time.time() + 30


def test_waiting_does_not_hold_the_registration_open(watch, monkeypatch):
    # Windows refuses the watcher's rewrite while anyone has the file open,
    # and reading it every 50 ms was often enough to lose the busy beat.
    opened = []
    real = ipc.read_json

    def counting(path):
        if path == ipc.registration_path(watch.root, watch.instance_id):
            opened.append(path)
        return real(path)

    turns = []

    def slow(_seconds):
        turns.append(1)
        if len(turns) == 40:
            watch.run_one(commands.next_command(watch.root, watch.instance_id))

    monkeypatch.setattr(time, "sleep", slow)
    target_ = target.Target(watch.root)
    monkeypatch.setattr(ipc, "read_json", counting)
    assert target_.run_one("ping", {})["ok"] is True
    assert len(opened) < 5


def test_ctrl_c_while_waiting_leaves_no_command_behind(watch, monkeypatch):
    def interrupt(_seconds):
        raise KeyboardInterrupt()
    monkeypatch.setattr(time, "sleep", interrupt)
    with pytest.raises(KeyboardInterrupt):
        cli.main(["ping"])
    assert commands.list_command_ids(watch.root, watch.instance_id) == []


# --- --timeout means one thing -------------------------------------------

def busy_since(root, seconds_ago):
    reg = instances.new_registration("softplc-9", 9, "ide",
                                     r"C:\p\softplc.project")
    instances.set_state(reg, instances.STATE_BUSY, ipc.now() - seconds_ago,
                        "import")
    instances.write(root, reg)
    return reg


def test_timeout_stretches_how_long_a_busy_ide_counts_as_alive(root, capsys,
                                                               monkeypatch):
    # Raising --timeout is exactly how a caller says "I will wait for this
    # long import". list honoured that; the target lookup ignored it and
    # pre-filtered on the hardcoded 120 seconds instead.
    busy_since(root, 200.0)
    cli.main(["list", "--timeout", "600"])
    assert "softplc-9" in capsys.readouterr().out

    reached = []

    def fake_send(root, instance_id, cmd, *args, **kwargs):
        reached.append(instance_id)
        return commands.new_result(cmd, True)

    monkeypatch.setattr(target, "send", fake_send)
    assert cli.main(["ping", "--timeout", "600"]) == EXIT_OK
    assert reached == ["softplc-9"]


def test_an_ide_that_crashed_mid_command_is_not_listed(root, capsys,
                                                       monkeypatch):
    # Its registration says busy for ever. The pid is the evidence the
    # heartbeat cannot be: a busy watcher never beats anyway.
    busy_since(root, 5.0)
    monkeypatch.setattr(process, "running", lambda pid, not_after=None:
                        False if pid == 9 else None)
    cli.main(["list", "--timeout", "600"])
    assert "softplc-9" not in capsys.readouterr().out
    assert cli.main(["ping", "--timeout", "600"]) == EXIT_TARGET


def test_the_default_timeout_still_writes_off_a_long_gone_command(root, capsys):
    busy_since(root, 200.0)
    assert cli.main(["ping"]) == EXIT_TARGET
    # ...but says it is busy rather than missing: "no live IDE found" sent
    # people looking for an IDE that was open in front of them.
    said = capsys.readouterr().err
    assert "softplc-9 has been busy for 200s running import" in said
    assert "--timeout" in said


# --- the watcher went away while we waited --------------------------------

def gone_after_first_wait(watch, monkeypatch):
    """Make the watcher vanish the moment the CLI settles in to wait."""
    def vanish(_seconds):
        instances.delete(watch.root, watch.instance_id)
    monkeypatch.setattr(time, "sleep", vanish)
    monkeypatch.setattr(target, "GONE_AFTER_S", 0.0)


def test_a_registration_blinking_out_mid_rewrite_is_not_death(watch,
                                                              monkeypatch):
    # IronPython has no os.replace, so the watcher's rewrite renames the file
    # aside and the new one in. Calling a healthy IDE dead on one missed
    # read made every other status come back "stopped before answering".
    path = ipc.registration_path(watch.root, watch.instance_id)
    saved = ipc.read_json(path)
    turns = []

    def blink(_seconds):
        turns.append(len(turns))
        if len(turns) == 1:
            ipc.remove_file(path)          # mid-rewrite: no file right now
            return
        ipc.write_json(path, saved)        # ...and it is back
        cmd = commands.next_command(watch.root, watch.instance_id)
        if cmd is not None:
            watch.run_one(cmd)

    monkeypatch.setattr(time, "sleep", blink)
    assert cli.main(["ping"]) == EXIT_OK


def test_stop_counts_a_vanished_watcher_as_success(watch, monkeypatch, capsys):
    # stop tears down one tick after answering, so the answer can be gone by
    # the time the CLI looks. The instance being gone IS the confirmation.
    gone_after_first_wait(watch, monkeypatch)
    assert cli.main(["stop"]) == EXIT_OK
    assert "gone" in capsys.readouterr().out


def test_any_other_command_says_the_watcher_died(watch, monkeypatch, capsys):
    gone_after_first_wait(watch, monkeypatch)
    assert cli.main(["export"]) == EXIT_FAILED
    assert "stopped before answering export" in capsys.readouterr().err


def gone_quiet(watch, monkeypatch, how):
    """Resolve the target, then let `how` kill the IDE behind it."""
    picked = target.Target(watch.root)
    how()
    polls = []
    monkeypatch.setattr(time, "sleep", lambda _seconds: polls.append(1))
    return picked, polls


def test_an_ide_that_died_mid_wait_is_not_waited_on(watch, monkeypatch):
    # It leaves its registration behind. The caller used to sit out the
    # whole --timeout on a file nobody would ever answer.
    picked, polls = gone_quiet(watch, monkeypatch, lambda: monkeypatch.setattr(
        process, "running", lambda pid, not_after=None: False))
    picked.timeout = 600.0
    with pytest.raises(cli.Failure) as raised:
        picked.run_one("export", {})
    assert "stopped before answering export" in str(raised.value)
    assert len(polls) < 5
    assert commands.list_command_ids(watch.root, watch.instance_id) == []


def stale_heartbeat(watch):
    reg = instances.read(watch.root, watch.instance_id)
    instances.stamp_heartbeat(reg, ipc.now() - instances.ALIVE_TIMEOUT_S - 5)
    instances.write(watch.root, reg)


def test_an_idle_watcher_that_stopped_beating_is_gone(watch, monkeypatch):
    picked, polls = gone_quiet(watch, monkeypatch,
                               lambda: stale_heartbeat(watch))
    picked.timeout = 600.0
    with pytest.raises(cli.Failure) as raised:
        picked.run_one("export", {})
    assert len(polls) < 5
    # Its process still runs, so the IDE may only be held by something of
    # its own, and "stopped" would send the reader looking for a crash.
    assert "stopped answering before export ran" in str(raised.value)
    assert "still runs" in str(raised.value)


def test_a_stopped_heartbeat_with_a_command_running_is_still_waited_on(
        watch, monkeypatch):
    # The busy write can be lost (WATCHER.md 5): somebody else's long
    # command is running, the record says idle and has stopped beating. The
    # running mark says the watcher is working, and our answer does come.
    picked = target.Target(watch.root)
    other = commands.write_command(watch.root, watch.instance_id, "import")
    commands.claim_command(watch.root, watch.instance_id, other["id"])
    stale_heartbeat(watch)
    turns = []

    def answer_later(_seconds):
        turns.append(1)
        if len(turns) == 40:
            commands.release_command(watch.root, watch.instance_id,
                                     other["id"])
            watch.run_one(commands.next_command(watch.root, watch.instance_id))
    monkeypatch.setattr(time, "sleep", answer_later)
    monkeypatch.setattr(target.instances, "HEARTBEAT_INTERVAL_S", 0.0)
    assert picked.run_one("ping", {})["ok"] is True


def test_a_target_is_found_through_its_rewrite_gap(watch, monkeypatch):
    # IronPython renames the registration aside and the new one in; a
    # lookup landing in between used to say "no live IDE found".
    path = ipc.registration_path(watch.root, watch.instance_id)
    saved = ipc.read_json(path)
    ipc.remove_file(path)
    ipc.write_json(path + ".tmp.src", saved)
    open(path + ".tmp", "w").close()

    def rename_lands(_seconds):
        ipc.write_json(path, saved)
        ipc.remove_file(path + ".tmp")
    monkeypatch.setattr(time, "sleep", rename_lands)
    assert target.Target(watch.root).instance_id == watch.instance_id


def test_no_ide_at_all_is_said_at_once(root, monkeypatch):
    # The retry is for a rewrite in progress, not a tax on every miss.
    slept = []
    monkeypatch.setattr(time, "sleep", lambda seconds: slept.append(seconds))
    with pytest.raises(cli.Failure):
        target.Target(root)
    assert slept == []


# --- compare's real answer is in data, not in what it printed --------------

def test_compare_shows_the_per_object_differences(watch, monkeypatch, capsys):
    # It used to be read off stdout_tail, which meant cdsint/report.py had a
    # branch naming one command by name. compare hands back the same list of
    # rows discover hands back for the type GUIDs it did not recognise, so
    # the summary prints it the way it prints any other list.
    watch.handlers["compare"] = lambda cmd, started: commands.new_result(
        cmd, True, started_at=started,
        messages=[commands.message("info", "modified 1, only on disk 0")],
        data={"different": 1, "changes": [{"name": "Newcomer",
                                           "path": "POUs/Newcomer.st",
                                           "state": "changed"}]},
        stdout_tail="200 lines of progress nobody asked for")
    answering(watch, monkeypatch)
    assert cli.main(["compare"]) == EXIT_OK
    printed = capsys.readouterr()
    assert "POUs/Newcomer.st" in printed.out
    assert "changed" in printed.out
    # And the tail stays where it belongs: a run that worked does not need it.
    assert "nobody asked for" not in printed.err


def test_a_successful_export_stays_quiet(watch, monkeypatch, capsys):
    watch.handlers["export"] = lambda cmd, started: commands.new_result(
        cmd, True, started_at=started,
        messages=[{"level": "info", "text": "Export complete!"}],
        stdout_tail="200 lines nobody asked for")
    answering(watch, monkeypatch)
    cli.main(["export"])
    assert "nobody asked for" not in capsys.readouterr().err

