# -*- coding: utf-8 -*-
"""plc trace in the watcher: through the person's login, polled across ticks.

The engine half: every check before the start, then a Recording whose poll()
the watcher calls once a tick. Nothing here waits; the fake clock moves only
when a test moves it.
"""
import pytest

from cds.core import trace_run
from engine import ide_private
from tests import plc_fakes
from tests.plc_fakes import TraceBench, UNTRIGGERED
from tests.plc_fakes import (   # noqa: F401  autouse fixtures
    fake_codesys_ui, keep_the_engine_loaded, workspace)


def run_only(**more):
    job = {"duration_s": 2.0, "out": plc_fakes.trace_job()["out"]}
    job.update(more)
    return job


@pytest.fixture
def bench(monkeypatch):
    bench = TraceBench(named="T1", trigger_script=UNTRIGGERED)
    monkeypatch.setattr(ide_private, "script_trace",
                        lambda tracer, handle, guid: bench.named_api)
    return bench


def started(bench, **job):
    answer = bench.watch(run_only(**job), "T1")
    assert answer.get(trace_run.RECORDING) is not None, answer["summary"]
    return answer[trace_run.RECORDING]


def finished(bench, recording):
    """Poll until the recording hands back its result, as ticks would."""
    for _tick in range(10):
        result = recording.poll()
        if result is not None:
            return result
    raise AssertionError("the recording never finished")


def test_it_starts_without_logging_in_or_out(bench):
    started(bench)
    assert bench.calls("login", "logout") == []
    assert bench.calls("download", "start") == [("download",), ("start",)]


def test_the_start_answers_that_it_is_recording(bench):
    answer = bench.watch(run_only(), "T1")
    assert answer["ok"] and "recording T1" in answer["summary"]


def test_it_answers_nothing_until_duration_s_is_up(bench):
    recording = started(bench)
    assert recording.poll() is None
    assert bench.calls("stop") == []
    bench.clock.now += 2.0
    assert recording.poll() is None          # stopped, now settling
    result = recording.poll()
    assert result["ok"], result["summary"]
    assert result["data"]["trace"] == "T1"
    assert result["data"]["stopped_early"] is None


def test_it_waits_for_the_trace_to_settle_after_stop(bench):
    recording = started(bench)
    bench.named_api.editor.settle = 99
    bench.clock.now += 2.0
    assert recording.poll() is None
    assert recording.poll() is None          # is_running still says True
    assert bench.calls("save") == bench.calls("save")[:1]  # configured only
    bench.clock.now += 5.0                   # past the grace
    assert recording.poll() is not None


def test_stop_ends_it_early_and_judges_what_it_recorded(bench):
    recording = started(bench)
    bench.clock.now += 0.5
    recording.stop("plc trace --stop")
    result = finished(bench, recording)
    assert result["data"]["stopped_early"] == {"after_s": 0.5,
                                               "why": "plc trace --stop"}
    assert result["data"]["duration_s"] == 0.5


def test_finish_saves_at_once(bench):
    recording = started(bench)
    bench.named_api.editor.settle = 99
    bench.clock.now += 1.0
    result = recording.finish("the watcher was stopped")
    assert result["data"]["stopped_early"]["why"] == "the watcher was stopped"
    assert ("stop",) in bench.log


def test_not_logged_in_is_refused_and_nothing_starts(bench):
    bench.online.session.is_logged_in = False
    answer = bench.watch(run_only(), "T1")
    assert not answer["ok"] and "log in" in answer["summary"]
    assert bench.calls("download", "start") == []


def test_a_trace_already_recording_is_left_alone(bench):
    bench.named_api.editor.running = True
    answer = bench.watch(run_only(), "T1")
    assert not answer["ok"] and "recording already" in answer["summary"]
    assert bench.calls("download", "start", "stop") == []


def test_without_a_name_the_watcher_refuses(bench):
    answer = bench.watch(plc_fakes.trace_job(), None)
    assert not answer["ok"] and "--name" in answer["summary"]
    assert bench.calls("download", "start") == []


def test_a_name_the_controller_does_not_have_is_refused_before_start(bench):
    bench.online.session.values.pop(plc_fakes.TRACED[0])
    answer = bench.watch(run_only(), "T1")
    assert not answer["ok"] and "do not resolve" in answer["summary"]
    assert bench.calls("download", "start") == []


def test_a_stopped_application_is_refused(bench):
    bench.online.session.application_state = "stop"
    answer = bench.watch(run_only(), "T1")
    assert not answer["ok"] and "records nothing" in answer["summary"]


def test_the_crc_is_not_read_and_says_why(bench):
    result = finished(bench, started_and_due(bench))
    assert result["data"]["crc"] == "UNKNOWN"
    assert any("CRC is not read" in note for note in result["data"]["notes"])
    assert bench.online.device.uploaded == []


def test_the_program_being_out_of_date_is_reported_not_refused(bench):
    bench.application.is_uptodate = False
    result = finished(bench, started_and_due(bench))
    assert result["data"]["uptodate"] is False


def started_and_due(bench):
    recording = started(bench)
    bench.clock.now += 2.0
    return recording


def test_a_poll_that_raises_is_a_failed_result_not_an_exception(bench):
    recording = started(bench)

    def lost():
        raise RuntimeError("connection lost")
    bench.named_api.editor.get_packet_state = lost
    bench.clock.now += 2.0
    result = finished(bench, recording)
    assert result["ok"] is False and "connection lost" in result["summary"]


def test_stop_in_the_project_form_is_refused(monkeypatch):
    from engine import entry_plc
    monkeypatch.setattr(entry_plc, "command_args", {"stop": True})
    answer = entry_plc.record()
    assert not answer["ok"] and "watcher" in answer["summary"]
