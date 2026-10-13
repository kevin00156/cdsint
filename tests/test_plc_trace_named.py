# -*- coding: utf-8 -*-
"""plc trace --name, headless: record a trace object as the project has it.

The trace's own definition is what is recorded; the job is only the run.
Nothing is created, and the project is still never saved.
"""
import pytest

from engine import ide_private
from tests import plc_fakes
from tests.plc_fakes import TASK, TraceBench
from tests.plc_fakes import (   # noqa: F401  autouse fixtures
    fake_codesys_ui, keep_the_engine_loaded, workspace)


def run_only():
    return {"duration_s": 1.0, "out": plc_fakes.trace_job()["out"]}


@pytest.fixture
def bench(monkeypatch):
    bench = TraceBench(named="T1")
    monkeypatch.setattr(ide_private, "script_trace",
                        lambda tracer, handle, guid: bench.named_api)
    return bench


def test_a_named_trace_records_what_it_is_set_to(bench):
    result = bench.run(job=run_only(), name="T1")
    assert result["ok"], result["summary"]
    assert result["data"]["trace"] == "T1"
    assert result["data"]["task"] == TASK
    assert bench.tracer.created == []


def test_a_named_trace_is_sized_for_the_run(bench):
    bench.run(job=run_only(), name="T1")
    assert bench.buffers.set_to is not None


def test_a_named_trace_with_nothing_to_record_is_refused(bench):
    bench.named_api.variables = []
    result = bench.run(job=run_only(), name="T1")
    assert not result["ok"]
    assert "T1 cannot record as it is set" in result["summary"]
    assert bench.calls("login") == []


def test_a_name_that_is_no_trace_is_refused_before_login(bench):
    result = bench.run(job=run_only(), name="T9")
    assert "no trace object named T9" in result["summary"]
    assert bench.calls("login") == []


def test_a_named_run_does_not_mind_an_existing_cdsint_trace(bench):
    # Only the unnamed run creates cdsint_trace, so only it refuses one.
    bench.project.names.append("cdsint_trace")
    result = bench.run(job=run_only(), name="T1")
    assert result["ok"], result["summary"]


def test_switched_off_variables_are_noted_and_not_recorded(bench):
    bench.named_api.disabled = set([plc_fakes.TRACED[1]])
    result = bench.run(job=run_only(), name="T1")
    assert any("switched off" in note for note in result["data"]["notes"])
    names = [call[1] for call in bench.calls("read_value")]
    assert plc_fakes.TRACED[1] not in names


def test_the_project_is_never_saved(bench):
    bench.run(job=run_only(), name="T1")
    assert bench.project.saves == 0
