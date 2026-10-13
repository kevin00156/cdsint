# -*- coding: utf-8 -*-
"""A plc trace in the watcher: claimed once, polled each tick, answered once.

The engine is stood in for by a handle with the Recording's three methods,
so this is the watcher's half only: it must not wait (SPEC D5), must keep
answering ping and status, must refuse everything else until the recording
ends, and must answer the caller however it ends.
"""
import pytest

from cds.core import commands, instances
from cds.ide import display, entries, session, watcher
from tests.fakes import make_globals

DONE = {"ok": True, "summary": "trace: recorded", "data": {"complete": True}}
TRACE_ARGS = {"name": "T1", "job": {"duration_s": 5.0, "out": "o"}}


class Handle(object):
    """The engine's Recording, as far as the watcher can see it."""

    def __init__(self, polls=2, result=None):
        self.polls_left = polls
        self.result = result or DONE
        self.stopped = None

    def poll(self):
        self.polls_left -= 1
        if self.stopped or self.polls_left <= 0:
            return self.result
        return None

    def stop(self, why):
        self.stopped = why

    def finish(self, why):
        self.stopped = why
        return self.result


@pytest.fixture
def root(tmp_path):
    return str(tmp_path)


@pytest.fixture(autouse=True)
def no_leftover_watcher():
    yield
    if session.current() is not None:
        delattr(session.sys, session.STATE_ATTR)


@pytest.fixture
def handle():
    return Handle()


@pytest.fixture
def watch(root, monkeypatch, handle):
    real = entries.answer

    def answer(ide, cmd, started):
        if cmd["command"] == "plc trace":
            return entries.Pending(ide, cmd, started, handle)
        return real(ide, cmd, started)
    monkeypatch.setattr(watcher.entries, "answer", answer)
    watch = watcher.Watcher(make_globals(), root)
    watch.start()
    return watch


def send(root, watch, command, args=None):
    return commands.write_command(root, watch.instance_id, command,
                                  args)["id"]


def result(root, watch, cmd_id):
    return commands.read_result(root, watch.instance_id, cmd_id)


def recording(root, watch, handle, polls=99):
    handle.polls_left = polls
    cmd_id = send(root, watch, "plc trace", TRACE_ARGS)
    watch.tick()
    return cmd_id


def test_the_watcher_runs_plc_trace_but_not_connect_or_download():
    assert "plc trace" in entries.COMMANDS
    assert set(entries.WATCHER_REFUSES) == {"plc connect", "plc download"}


def test_the_caller_is_answered_once_the_recording_is_done(root, watch):
    cmd_id = send(root, watch, "plc trace", TRACE_ARGS)
    watch.tick()                       # claimed, started
    assert result(root, watch, cmd_id) is None
    watch.tick()                       # first poll: still going
    assert result(root, watch, cmd_id) is None
    watch.tick()                       # second poll: done
    assert result(root, watch, cmd_id)["ok"] is True
    assert watch.recording is None
    assert commands.running_since(root, watch.instance_id) is None


def test_while_recording_the_command_stays_claimed(root, watch, handle):
    recording(root, watch, handle)
    assert commands.running_since(root, watch.instance_id) is not None


def test_while_recording_the_registration_says_so(root, watch, handle):
    recording(root, watch, handle)
    reg = instances.read(root, watch.instance_id)
    assert reg["state"] == instances.STATE_RECORDING
    assert instances.is_alive(reg)


def test_after_the_recording_the_registration_is_idle(root, watch, handle):
    recording(root, watch, handle, polls=1)
    watch.tick()
    reg = instances.read(root, watch.instance_id)
    assert reg["state"] == instances.STATE_IDLE


def test_while_recording_other_commands_are_refused_with_when(root, watch,
                                                              handle):
    recording(root, watch, handle)
    other = send(root, watch, "export")
    watch.tick()
    refused = result(root, watch, other)
    assert refused["ok"] is False and "recording" in refused["error"]
    assert "until about" in refused["error"] and "--stop" in refused["error"]
    reg = instances.read(root, watch.instance_id)
    assert reg["state"] == instances.STATE_RECORDING


def test_while_recording_a_second_trace_is_refused(root, watch, handle):
    recording(root, watch, handle)
    second = send(root, watch, "plc trace", TRACE_ARGS)
    watch.tick()
    assert result(root, watch, second)["ok"] is False


def test_while_recording_ping_still_answers(root, watch, handle):
    recording(root, watch, handle)
    ping = send(root, watch, "ping")
    watch.tick()
    assert result(root, watch, ping)["ok"] is True


def test_stop_ends_the_recording_and_both_callers_are_answered(root, watch,
                                                               handle):
    first = recording(root, watch, handle)
    stop = send(root, watch, "plc trace", {"stop": True})
    watch.tick()
    assert result(root, watch, stop)["ok"] is True
    assert handle.stopped == "plc trace --stop"
    watch.tick()
    assert result(root, watch, first)["ok"] is True


def test_stop_with_nothing_recording_says_so(root, watch):
    stop = send(root, watch, "plc trace", {"stop": True})
    watch.tick()
    answered = result(root, watch, stop)
    assert answered["ok"] is False
    assert "nothing is recording" in answered["error"]


def test_a_poll_that_raises_still_answers_the_caller(root, watch, handle):
    def broken():
        raise RuntimeError("the IDE fell over")
    handle.poll = broken
    first = send(root, watch, "plc trace", TRACE_ARGS)
    watch.tick()
    watch.tick()
    answered = result(root, watch, first)
    assert answered["ok"] is False and "fell over" in answered["error"]
    assert watch.recording is None


def test_a_failed_recording_is_answered_as_failed(root, watch, handle):
    handle.result = {"ok": False, "summary": "trace: samples are missing",
                     "data": {"complete": False}}
    first = recording(root, watch, handle, polls=1)
    watch.tick()
    answered = result(root, watch, first)
    assert answered["ok"] is False
    assert "samples are missing" in answered["error"]
    assert answered["data"] == {"complete": False}


def test_closing_the_watcher_finishes_the_recording(root, watch, handle,
                                                    monkeypatch):
    first = recording(root, watch, handle)
    written = {}
    real_write = commands.write_result

    def keep(root_, instance_id, record):
        written[record["id"]] = record
        real_write(root_, instance_id, record)
    monkeypatch.setattr(commands, "write_result", keep)
    watch.shutdown()
    assert written[first]["ok"] is True
    assert handle.stopped == "the watcher was stopped"


def test_the_watchers_own_stop_is_refused_while_recording(root, watch,
                                                          handle):
    recording(root, watch, handle)
    stop = send(root, watch, "stop")
    watch.tick()
    assert result(root, watch, stop)["ok"] is False
    assert watch.running is True


def test_the_window_says_it_is_recording(root, watch, handle):
    recording(root, watch, handle)
    shown = display.describe(watch)
    assert shown["headline"].startswith("RECORDING")
    assert shown["level"] == display.BUSY


def test_a_recording_registration_lives_by_its_heartbeat():
    reg = instances.new_registration("w-1", 1, "softplc", "C:/p/s.project",
                                     now=1000.0)
    instances.set_state(reg, instances.STATE_RECORDING, 1000.0, "plc trace")
    assert instances.is_alive(reg, now=1005.0)
    assert not instances.is_alive(reg, now=1000.0 + 3600.0)
