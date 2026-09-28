# -*- coding: utf-8 -*-
"""Tests for cds.ide.watcher and the arming half in cds.ide.session.

The watcher takes the CODESYS globals as an argument instead of reaching for
them, and its timer comes from an injected factory, so a fake `system`, a fake
`projects` and a fake timer are enough to drive everything under CPython.
What this cannot show is whether the real IDE is clickable while the watcher
runs — that needs real mouse input (docs/WATCHER.md 8).
"""
import os
import sys

import pytest

from cds.core import commands, instances, ipc
from cds.ide import session, watcher
from tests.fakes import FakeTimer, Project, Projects, make_globals


@pytest.fixture
def root(tmp_path):
    return str(tmp_path)


@pytest.fixture(autouse=True)
def no_leftover_watcher():
    """A watcher parks itself on sys; never let one leak between tests."""
    yield
    if session.current() is not None:
        delattr(session.sys, session.STATE_ATTR)


# --- registration ----------------------------------------------------------

def test_the_watcher_registers_itself_on_start(root):
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    reg = instances.read(root, watch.instance_id)
    assert reg["project_name"] == "softplc"
    assert reg["pid"] == os.getpid()
    assert instances.is_alive(reg)


def test_start_makes_the_command_and_result_directories(root):
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    assert os.path.isdir(ipc.command_dir(root, watch.instance_id))
    assert os.path.isdir(ipc.result_dir(root, watch.instance_id))


def test_shutdown_leaves_nothing_behind(root):
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    watch.shutdown()
    assert instances.read(root, watch.instance_id) is None
    assert not os.path.exists(ipc.instance_dir(root, watch.instance_id))


def test_a_second_watcher_in_the_same_ide_is_refused(root):
    ide = make_globals()
    watcher.Watcher(ide, root).start()
    with pytest.raises(RuntimeError):
        watcher.Watcher(ide, root).start()


def test_a_stale_registration_is_cleared_on_start(root):
    dead = instances.new_registration("ghost-1", 9, "old", "C:\\p\\ghost.project",
                                      now=ipc.now() - 600.0)
    instances.write(root, dead)
    watcher.Watcher(make_globals(), root).start()
    assert instances.read(root, "ghost-1") is None


def test_start_sweeps_results_nobody_collected(root):
    watch = watcher.Watcher(make_globals(), root)
    ipc.ensure_dirs(root, watch.instance_id)
    commands.write_result(root, watch.instance_id, {"id": "old-1", "ok": True})
    stale = os.path.join(ipc.result_dir(root, watch.instance_id), "old-1.json")
    os.utime(stale, (ipc.now() - 7200.0, ipc.now() - 7200.0))
    watch.start()
    assert commands.read_result(root, watch.instance_id, "old-1") is None


# --- the heartbeat ---------------------------------------------------------

def test_the_heartbeat_waits_its_turn(root):
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    now = ipc.now()
    assert watch.beat_if_due(now + 0.5) is False
    assert watch.beat_if_due(now + instances.HEARTBEAT_INTERVAL_S + 1.0) is True


def test_a_locked_registration_defers_the_beat_instead_of_killing_it(root,
                                                                     monkeypatch):
    # A CLI reading the file holds it open, and Windows will not let the
    # rename land. That is a missed beat, not the end of the watcher.
    watch = watcher.Watcher(make_globals(), root)
    watch.start()

    def locked(_root, _reg):
        raise OSError(13, "used by another process")

    monkeypatch.setattr(instances, "write", locked)
    now = ipc.now() + instances.HEARTBEAT_INTERVAL_S + 1.0
    assert watch.beat_if_due(now) is False
    monkeypatch.undo()
    # _last_beat was left alone, so the very next turn retries.
    assert watch.beat_if_due(now) is True


def test_a_long_lock_is_reported_once_not_every_turn(root, monkeypatch, capsys):
    # The retry happens on every tick; saying so each time would bury the
    # IDE's message view under hundreds of identical lines.
    watch = watcher.Watcher(make_globals(), root)
    watch.start()

    def locked(_root, _reg):
        raise OSError(13, "used by another process")

    monkeypatch.setattr(instances, "write", locked)
    now = ipc.now()
    for turn in range(20):
        watch.beat_if_due(now + instances.HEARTBEAT_INTERVAL_S + turn)
    assert capsys.readouterr().out.count("heartbeat deferred") == 1


def test_a_locked_registration_does_not_break_shutdown(root, monkeypatch):
    watch = watcher.Watcher(make_globals(), root)
    watch.start()

    def locked(_root, _instance_id):
        raise OSError(13, "used by another process")

    monkeypatch.setattr(instances, "delete", locked)
    watch.shutdown()  # the reason the loop stopped must not be buried here


# --- one command -----------------------------------------------------------

def run(watch, name, args=None):
    """Queue a command, let the watcher take it, hand back the result."""
    cmd = commands.write_command(watch.root, watch.instance_id, name, args)
    watch.run_one(commands.next_command(watch.root, watch.instance_id))
    return commands.take_result(watch.root, watch.instance_id, cmd["id"])


def test_ping_answers(root):
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    result = run(watch, "ping")
    assert result["ok"] is True
    assert "pong" in result["messages"][0]["text"]


def test_status_reports_the_project_that_is_open_now(root):
    ide = make_globals()
    watch = watcher.Watcher(ide, root)
    watch.start()
    ide["projects"].primary = Project(path="C:\\p\\boiler.project")
    result = run(watch, "status")
    assert result["data"]["project_name"] == "boiler"
    assert result["data"]["instance_id"] == watch.instance_id


def test_status_does_not_report_itself_as_busy(root):
    # The watcher is busy *because* it is answering status, which tells the
    # caller nothing. `list` is where the live state belongs.
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    data = run(watch, "status")["data"]
    assert data["state"] == instances.STATE_IDLE
    assert data["busy_since"] is None


def test_status_survives_the_project_being_closed(root):
    ide = make_globals()
    watch = watcher.Watcher(ide, root)
    watch.start()
    ide["projects"].primary = None
    assert run(watch, "status")["data"]["project_path"] is None


def test_stop_takes_the_watcher_out_of_service(root):
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    assert run(watch, "stop")["ok"] is True
    assert watch.running is False


def test_an_unknown_command_fails_loudly_and_says_what_it_knows(root):
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    result = run(watch, "frobnicate")
    assert result["ok"] is False
    assert "frobnicate" in result["error"] and "ping" in result["error"]


def test_a_handler_that_raises_becomes_a_failed_result(root):
    watch = watcher.Watcher(make_globals(), root)
    watch.start()

    def boom(cmd, started):
        raise ValueError("the IDE said no")

    watch.handlers["ping"] = boom
    result = run(watch, "ping")
    assert result["ok"] is False
    assert "the IDE said no" in result["error"]


def test_a_command_its_caller_gave_up_on_is_answered_and_not_run(root):
    # A CLI killed while it waited cannot take its command back out of the
    # queue. Without a deadline an import queued yesterday ran whenever the
    # watcher next got to it, with nobody left to read the answer.
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    ran = []
    watch.handlers["import"] = lambda cmd, started: ran.append(cmd)
    cmd = commands.write_command(root, watch.instance_id, "import",
                                 {"yes": True}, now=ipc.now() - 600.0,
                                 deadline=ipc.now() - 480.0)
    watch.tick()
    result = commands.read_result(root, watch.instance_id, cmd["id"])
    assert ran == []
    assert result["ok"] is False
    assert "stopped waiting" in result["error"] and "not run" in result["error"]


def test_a_command_with_no_deadline_still_runs_however_old(root):
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    cmd = commands.write_command(root, watch.instance_id, "ping",
                                 now=ipc.now() - 86400.0)
    watch.tick()
    assert commands.read_result(root, watch.instance_id,
                                cmd["id"])["ok"] is True


def test_a_command_is_claimed_before_it_runs(root):
    # A watcher that dies mid-command must not find it queued again.
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    seen = {}

    def check(cmd, started):
        seen["queued"] = commands.list_command_ids(root, watch.instance_id)
        return commands.new_result(cmd, True, started_at=started)

    watch.handlers["ping"] = check
    run(watch, "ping")
    assert seen["queued"] == []


def test_a_running_command_leaves_its_mark_until_it_is_answered(root):
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    seen = {}

    def check(cmd, started):
        seen["since"] = commands.running_since(root, watch.instance_id)
        return commands.new_result(cmd, True, started_at=started)

    watch.handlers["ping"] = check
    run(watch, "ping")
    assert seen["since"] is not None
    assert commands.running_since(root, watch.instance_id) is None


def test_a_command_taken_back_before_the_claim_is_not_run(root):
    # The CLI timed out and deleted it between next_command and the claim.
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    ran = []
    watch.handlers["ping"] = lambda cmd, started: ran.append(cmd)
    cmd = commands.write_command(root, watch.instance_id, "ping")
    queued = commands.next_command(root, watch.instance_id)
    commands.delete_command(root, watch.instance_id, cmd["id"])
    assert watch.run_one(queued) is None
    assert ran == [] and watch.done == 0
    assert commands.read_result(root, watch.instance_id, cmd["id"]) is None


def test_a_busy_beat_the_cli_got_in_the_way_of_is_tried_again_at_once(
        root, monkeypatch):
    # The next turn is after the command. Losing this one write left the
    # record idle with a heartbeat that stopped for the whole of an import,
    # and another IDE's start-up pruned the directory out from under it.
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    real = instances.write
    refused = []

    def open_elsewhere_once(root_, reg):
        if reg["state"] == instances.STATE_BUSY and not refused:
            refused.append(reg["state"])
            raise OSError(13, "used by another process")
        return real(root_, reg)

    monkeypatch.setattr(instances, "write", open_elsewhere_once)
    seen = {}

    def long_import(cmd, started):
        seen["state"] = instances.read(root, watch.instance_id)["state"]
        seen["pruned"] = instances.prune_stale(root, now=ipc.now() + 300.0)
        return commands.new_result(cmd, True, started_at=started)

    watch.handlers["import"] = long_import
    run(watch, "import", {"yes": True})
    assert refused and seen == {"state": instances.STATE_BUSY, "pruned": []}


def test_a_command_in_progress_is_spared_even_if_busy_never_got_written(
        root, monkeypatch):
    # Every retry refused: the record says idle, the heartbeat stops. The
    # running mark is what another IDE's start-up still sees.
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    real = instances.write

    def never_busy(root_, reg):
        if reg["state"] == instances.STATE_BUSY:
            raise OSError(13, "used by another process")
        return real(root_, reg)

    monkeypatch.setattr(instances, "write", never_busy)
    seen = {}

    def long_import(cmd, started):
        seen["state"] = instances.read(root, watch.instance_id)["state"]
        seen["pruned"] = instances.prune_stale(root, now=ipc.now() + 300.0)
        seen["dir"] = os.path.isdir(ipc.result_dir(root, watch.instance_id))
        return commands.new_result(cmd, True, started_at=started)

    watch.handlers["import"] = long_import
    assert run(watch, "import", {"yes": True})["ok"] is True
    assert seen == {"state": instances.STATE_IDLE, "pruned": [], "dir": True}


def test_the_instance_goes_busy_while_a_command_runs(root):
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    seen = {}

    def check(cmd, started):
        seen["state"] = instances.read(root, watch.instance_id)["state"]
        return commands.new_result(cmd, True, started_at=started)

    watch.handlers["ping"] = check
    run(watch, "ping")
    assert seen["state"] == instances.STATE_BUSY
    assert instances.read(root, watch.instance_id)["state"] == instances.STATE_IDLE


def test_answering_sweeps_results_nobody_came_back_for(root):
    # A caller that timed out leaves its result behind; a watcher that runs
    # for days would otherwise collect them forever.
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    commands.write_result(root, watch.instance_id, {"id": "old-1", "ok": True})
    stale = os.path.join(ipc.result_dir(root, watch.instance_id), "old-1.json")
    os.utime(stale, (ipc.now() - 7200.0, ipc.now() - 7200.0))
    fresh = run(watch, "ping")
    assert commands.read_result(root, watch.instance_id, "old-1") is None
    assert fresh["ok"] is True  # and the answer just written survived


# --- the tick --------------------------------------------------------------

def test_a_tick_answers_one_queued_command(root):
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    commands.write_command(root, watch.instance_id, "ping",
                           cmd_id="1725453665000-aaaaaa")
    assert watch.tick() is True
    assert commands.read_result(root, watch.instance_id,
                                "1725453665000-aaaaaa")["ok"] is True


def test_an_idle_tick_just_beats(root):
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    assert watch.tick() is True
    assert commands.list_command_ids(root, watch.instance_id) == []


def test_a_tick_that_arrives_mid_command_turns_straight_around(root):
    # An import pumps messages of its own, so the timer fires again while the
    # import is still going. Two imports at once would be a disaster.
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    seen = []

    def reentrant(cmd, started):
        seen.append(watch.tick())  # the timer, firing inside the command
        return commands.new_result(cmd, True, started_at=started)

    watch.handlers["ping"] = reentrant
    commands.write_command(root, watch.instance_id, "ping")
    watch.tick()
    assert seen == [False]


def test_a_tick_never_lets_an_exception_escape(root, capsys):
    # An exception out of a WinForms handler becomes a thread-exception dialog.
    watch = watcher.Watcher(make_globals(), root)
    watch.start()

    def boom(*args, **kwargs):
        raise KeyboardInterrupt("even a BaseException")

    watch.beat_if_due = boom
    assert watch.tick() is True
    assert "tick failed" in capsys.readouterr().out
    assert watch.busy is False  # and the guard was released


def test_not_even_system_exit_escapes_a_tick(root, capsys):
    # "Catch everything inside a tick" (WATCHER.md 5) had one exception, and
    # it was the one a body's sys.exit() raises.
    watch = watcher.Watcher(make_globals(), root)
    watch.start()

    def leave(*args, **kwargs):
        raise SystemExit(3)

    watch.beat_if_due = leave
    assert watch.tick() is True
    assert "tick failed" in capsys.readouterr().out


# --- arming and disarming --------------------------------------------------

def test_main_arms_a_timer_and_returns(root):
    made = []

    def factory(interval_ms, handler):
        made.append(FakeTimer(interval_ms, handler))
        return made[-1]

    watch = session.main(make_globals(), root, timer_factory=factory)
    assert made[0].interval_ms == session.TICK_MS
    assert session.current() is watch
    assert instances.is_alive(instances.read(root, watch.instance_id))
    made[0].handler()  # a WinForms tick arrives with no arguments used here
    assert watch.running is True


def test_running_the_script_again_stops_the_watcher(root):
    timers = []

    def factory(interval_ms, handler):
        timers.append(FakeTimer(interval_ms, handler))
        return timers[-1]

    watch = session.main(make_globals(), root, timer_factory=factory)
    assert session.main(make_globals(), root, timer_factory=factory) is None
    assert len(timers) == 1  # the second run stopped, it did not start
    assert timers[0].started is False and timers[0].disposed is True
    assert session.current() is None
    assert instances.read(root, watch.instance_id) is None


def test_the_stop_command_tears_down_on_the_following_tick(root):
    # The answer to `stop` has to survive long enough to be collected.
    timers = []

    def factory(interval_ms, handler):
        timers.append(FakeTimer(interval_ms, handler))
        return timers[-1]

    watch = session.main(make_globals(), root, timer_factory=factory)
    on_tick = timers[0].handler
    cmd = commands.write_command(root, watch.instance_id, "stop")
    on_tick()
    assert commands.read_result(root, watch.instance_id, cmd["id"])["ok"] is True
    assert timers[0].started is True  # still there for the caller to read it

    on_tick()
    assert timers[0].started is False and timers[0].disposed is True
    assert instances.read(root, watch.instance_id) is None
    assert session.current() is None


def armed(root):
    """A watcher armed through session.main, and the timer it hung."""
    timers = []

    def factory(interval_ms, handler):
        timers.append(FakeTimer(interval_ms, handler))
        return timers[-1]

    return session.main(make_globals(), root, timer_factory=factory), timers


def test_stop_mid_command_waits_for_the_command_to_finish(root):
    # The Stop button and a re-run of the script both arrive while a command
    # pumps messages. Tearing down there pulled cmd/ and result/ out from
    # under the command, and its finally then wrote the registration back.
    watch, timers = armed(root)
    seen = {}

    def stopped_midway(cmd, started):
        session.stop(watch)
        seen["dir"] = os.path.isdir(ipc.result_dir(root, watch.instance_id))
        timers[0].handler()            # the timer fires inside the command
        seen["still"] = session.current() is watch
        return commands.new_result(cmd, True, started_at=started)

    watch.handlers["ping"] = stopped_midway
    cmd = commands.write_command(root, watch.instance_id, "ping")
    timers[0].handler()
    assert seen == {"dir": True, "still": True}
    assert commands.read_result(root, watch.instance_id, cmd["id"])["ok"]

    timers[0].handler()                # the first tick after it tears down
    assert session.current() is None
    assert timers[0].disposed is True
    assert instances.read(root, watch.instance_id) is None
    assert not os.path.exists(ipc.instance_dir(root, watch.instance_id))


def test_rerunning_the_script_mid_command_stops_after_it(root):
    watch, timers = armed(root)

    def rerun_midway(cmd, started):
        assert session.main(make_globals(), root) is None
        return commands.new_result(cmd, True, started_at=started)

    watch.handlers["ping"] = rerun_midway
    commands.write_command(root, watch.instance_id, "ping")
    timers[0].handler()
    assert watch.running is False and session.current() is watch
    timers[0].handler()
    assert session.current() is None
    assert instances.read(root, watch.instance_id) is None


# --- staying answerable when writing the answer fails ----------------------

def test_a_failure_after_the_command_still_puts_the_state_back(root,
                                                               monkeypatch):
    # Stuck in busy is worse than a lost answer: once busy_since goes stale
    # the CLI stops seeing the instance, and prune_stale keeps sparing it
    # because the heartbeat is fresh. Nothing recovers from that on its own.
    watch = watcher.Watcher(make_globals(), root)
    watch.start()

    def boom(*args, **kwargs):
        raise OSError(13, "used by another process")

    monkeypatch.setattr(commands, "write_result", boom)
    cmd = commands.write_command(root, watch.instance_id, "ping")
    watch.run_one(commands.next_command(root, watch.instance_id))
    assert instances.read(root, watch.instance_id)["state"] == \
        instances.STATE_IDLE
    assert watch.tick() is True  # and the watcher is still in service
    assert cmd["id"]


def test_a_command_is_still_claimed_when_answering_fails(root, monkeypatch):
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    monkeypatch.setattr(commands, "prune_results",
                        lambda *a, **k: 1 / 0)
    commands.write_command(root, watch.instance_id, "ping")
    watch.run_one(commands.next_command(root, watch.instance_id))
    assert commands.list_command_ids(root, watch.instance_id) == []


# --- following the project the IDE has open now ----------------------------

def test_the_registration_follows_a_project_swap(root):
    # `list` is how a caller picks its target; a name frozen at start-up means
    # it picks the wrong IDE or none at all.
    ide = make_globals()
    watch = watcher.Watcher(ide, root)
    watch.start()
    ide["projects"].primary = Project(path=r"C:\p\boiler.project")
    watch.beat_if_due(ipc.now() + instances.HEARTBEAT_INTERVAL_S + 1.0)
    reg = instances.read(root, watch.instance_id)
    assert reg["project_name"] == "boiler"
    assert reg["instance_id"] == watch.instance_id  # the directory keeps its name


def watching_a_project_with(tmp_path, values):
    """An IDE with a project open, and a settings file written beside it.

    Its own directory, not the instances root the `root` fixture hands out:
    a stray .json in there is a registration as far as prune_stale is
    concerned.
    """
    from cds.core import settings
    home = os.path.join(str(tmp_path), "proj")
    os.makedirs(home)
    path = os.path.join(home, "softplc.project")
    settings.write(settings.path_for(path), values)
    return make_globals(path), home


def test_the_sync_folder_is_reported(root, tmp_path):
    absolute = "D:" + os.sep + "work" + os.sep + "sync"
    ide, _home = watching_a_project_with(tmp_path, {"sync_folder": absolute})
    watch = watcher.Watcher(ide, root)
    watch.start()
    assert instances.read(root, watch.instance_id)["sync_dir"] == absolute


def test_a_relative_sync_folder_resolves_against_the_project(root, tmp_path):
    ide, home = watching_a_project_with(tmp_path, {"sync_folder": "./export"})
    watch = watcher.Watcher(ide, root)
    watch.start()
    reg = instances.read(root, watch.instance_id)
    assert reg["sync_dir"] == os.path.join(home, "export")



def test_an_unset_sync_folder_reads_as_nothing(root):
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    assert instances.read(root, watch.instance_id)["sync_dir"] is None


def test_the_ide_field_names_the_product(root):
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    # IronPython 2.7.7 is both Delta 1.10 and Lenze 3.24, so the version
    # string alone cannot tell them apart.
    assert os.path.basename(sys.executable) in \
        instances.read(root, watch.instance_id)["ide"]


def test_globals_without_system_are_refused_at_once(root):
    # TypeError, not KeyError: what is wrong is the argument, and a KeyError
    # out of a constructor reads as a lookup that went wrong inside it.
    with pytest.raises(TypeError):
        watcher.Watcher({"projects": Projects(None)}, root)


# --- feeding the status window ---------------------------------------------

def test_a_command_paints_busy_before_it_starts_working(root):
    # The IDE stops repainting for the whole of an export, so a BUSY drawn
    # afterwards is a BUSY nobody ever saw.
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    seen = []
    watch.display_to = lambda picture: seen.append(picture["headline"])

    def slow(cmd, started):
        seen.append("...working...")
        return commands.new_result(cmd, True, started_at=started)

    watch.handlers["export"] = slow
    run(watch, "export")
    assert seen[0] == "BUSY: export"
    assert seen[1] == "...working..."
    assert seen[-1] == "LISTENING"


def test_the_watcher_remembers_how_the_last_command_went(root):
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    run(watch, "ping")
    assert watch.done == 1
    assert watch.last["command"] == "ping" and watch.last["ok"] is True
    assert watch.doing is None


def test_a_failed_command_is_remembered_as_failed(root):
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    run(watch, "frobnicate")
    assert watch.last["ok"] is False


def test_a_window_that_throws_cannot_stop_the_watcher(root, capsys):
    watch = watcher.Watcher(make_globals(), root)
    watch.start()

    def broken(_picture):
        raise RuntimeError("the form is gone")

    watch.display_to = broken
    assert run(watch, "ping")["ok"] is True
    assert "status window failed" in capsys.readouterr().out


def test_nothing_is_pushed_when_there_is_no_window(root):
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    assert watch.display_to is None
    run(watch, "ping")  # must not raise
