# -*- coding: utf-8 -*-
"""plc trace on a fake bench: the ring's memory, types, trigger and condition.

The same bench as tests/test_plc_trace.py. What is pinned here is what
docs/trace-research.md 13.4 and 13.5 measured: a trace that stopped itself
refuses stop(), a condition that is not a BOOL variable fails start()
naming nothing, and a ring too big for the controller is not refused by
the controller.
"""
import os

from tests.plc_fakes import (TRIGGER_NEVER, TRIGGER_UNFINISHED, Buffers,
                             TraceBench)
from tests.plc_fakes import (   # noqa: F401  autouse fixtures
    fake_codesys_ui, keep_the_engine_loaded, workspace)
import tests.plc_fakes as plc_fakes

COUNTER = "GVL.udiProbeCnt"
PULSE = "GVL.xProbePulse"
TRIGGER = {"variable": COUNTER, "edge": "rising", "level": 5000,
           "post_samples": 2000}


def values(**extra):
    found = dict(plc_fakes.VALUES)
    found.update({COUNTER: "UDINT#1234", PULSE: "FALSE"})
    found.update(extra)
    return found


def bench_with(**kwargs):
    kwargs.setdefault("values", values())
    return TraceBench(**kwargs)


def trigger_job(**changes):
    trigger = dict(TRIGGER)
    trigger.update(changes)
    return plc_fakes.trace_job(trigger=trigger, duration_s=10.0)


class LoggedBuffers(Buffers):
    """The buffer seam, putting its call in the bench's log."""

    def __init__(self, log):
        Buffers.__init__(self)
        self.log = log

    def __call__(self, api):
        set_buffers = Buffers.__call__(self, api)

        def logged(ring, per_variable):
            self.log.append(("set_buffers", ring, per_variable))
            set_buffers(ring, per_variable)
        return logged


# --------------------------------------------------------------------------
# The buffers wait for the types
# --------------------------------------------------------------------------

def test_the_buffers_are_set_after_the_names_and_before_the_download():
    bench = bench_with()
    bench.buffers = LoggedBuffers(bench.log)
    result = bench.run()
    assert result["ok"], result["summary"]
    kinds = [call[0] for call in bench.log]
    last_read = max(i for i, kind in enumerate(kinds) if kind == "read_value")
    assert last_read < kinds.index("set_buffers") < kinds.index("download")


def test_a_ring_over_trace_memory_mb_is_refused_before_the_download():
    # 1 ms for an hour: 3600000 entries of 12 + 4 + 2 bytes, about 62 MB.
    bench = bench_with(settings_file={"trace_memory_mb": 16})
    result = bench.run(plc_fakes.trace_job(duration_s=3600))
    assert not result["ok"]
    summary = result["summary"]
    assert "61.8 MB" in summary and "16 MB" in summary
    assert "trace_memory_mb" in summary
    assert bench.calls("download", "start", "open_editor") == []
    assert bench.buffers.set_to is None and bench.calls("logout")
    assert result["data"]["buffer"]["controller_bytes"] == 3600000 * 18


def test_the_default_limit_takes_a_short_recording():
    bench = bench_with()
    result = bench.run(plc_fakes.trace_job(duration_s=60))
    assert result["ok"], result["summary"]


def test_a_variable_of_unknown_type_is_refused_by_name():
    bench = bench_with(values=values(**{"PRG_AxisControl._iOvrZone": "3"}))
    result = bench.run()
    assert not result["ok"]
    assert result["data"]["failed_objects"] == ["PRG_AxisControl._iOvrZone"]
    assert "PRG_AxisControl._iOvrZone read back as '3' (type unknown)" in \
        result["summary"]
    assert bench.calls("download", "open_editor") == []
    assert bench.buffers.set_to is None


def test_a_type_with_no_known_size_is_refused_by_name():
    bench = bench_with(values=values(
        **{"PRG_AxisControl._iOvrZone": "E_Zone#Left"}))
    result = bench.run()
    assert not result["ok"] and "type E_ZONE" in result["summary"]
    assert bench.calls("download") == []


def test_a_plain_trace_that_stopped_early_fails_and_is_not_stopped_again():
    # Nothing in the timestamps says a recording ended early: completeness
    # is judged over the span the samples cover.
    bench = bench_with(trigger_script=None)
    bench.tracer.api.editor.start = lambda: setattr(
        bench.tracer.api.editor, "script", [("Stopped", "Disabled")])
    result = bench.run()
    assert not result["ok"]
    assert "was Stopped before duration_s" in result["summary"]
    assert bench.calls("stop") == []
    assert all(os.path.isfile(path)
               for path in result["data"]["files"].values())


# --------------------------------------------------------------------------
# Trigger
# --------------------------------------------------------------------------

def test_a_trigger_is_set_in_full_and_enabled_last():
    bench = bench_with()
    bench.run(trigger_job(edge="falling", level=12.5))
    api = bench.tracer.api
    assert api.assigned == [
        ("trigger_variable", COUNTER),
        ("trigger_edge", plc_fakes.TriggerEdge.Negative),
        ("trigger_level", "12.5"),
        ("post_trigger_samples", 2000),
        ("trigger_enabled", True)]


def test_each_edge_word_is_its_enum_member():
    for word, member in (("rising", "Positive"), ("falling", "Negative"),
                         ("both", "Both")):
        bench = bench_with()
        bench.run(trigger_job(edge=word))
        assert bench.tracer.api.trigger_edge.name == member


def test_a_trigger_that_fires_ends_the_wait_and_is_not_stopped_again():
    bench = bench_with()
    result = bench.run(trigger_job())
    assert result["ok"], result["summary"]
    data = result["data"]
    assert data["trigger"] == {"reached": True}
    assert data["complete"] is True
    # it stopped itself on the third poll, far short of 10 s of holds
    assert len(bench.calls("hold")) == 2
    assert bench.calls("stop") == []
    assert len(bench.calls("save")) == 2


def test_a_trigger_run_reports_exactly_the_spec_shape_plus_trigger():
    data = bench_with().run(trigger_job())["data"]
    assert set(data) == {
        "action", "controller", "crc", "task", "period_us", "resolution",
        "duration_s", "buffer", "files", "variables", "complete", "trigger",
        "failed_objects", "why", "notes", "workspace"}


def test_a_trigger_that_never_comes_fails_with_its_files_written():
    bench = bench_with(trigger_script=TRIGGER_NEVER)
    result = bench.run(trigger_job())
    assert not result["ok"]
    data = result["data"]
    assert data["trigger"] == {"reached": False}
    assert "never came" in data["why"] and COUNTER in data["why"]
    assert len(bench.calls("hold")) == 50            # all of duration_s
    assert bench.calls("stop") == [("stop",)]       # Started, so stopped
    assert all(os.path.isfile(path) for path in data["files"].values())
    assert data["variables"]                        # judged all the same


def test_a_trigger_that_came_but_did_not_finish_says_so():
    bench = bench_with(trigger_script=TRIGGER_UNFINISHED)
    result = bench.run(trigger_job())
    assert not result["ok"]
    assert result["data"]["trigger"] == {"reached": True}
    assert "came, but the trace had not kept its 2000 samples" in \
        result["summary"]
    assert bench.calls("stop") == [("stop",)]


def test_the_trigger_variable_is_read_with_the_others():
    bench = bench_with()
    bench.run(trigger_job())
    read = [call[1] for call in bench.calls("read_value")]
    assert read == plc_fakes.TRACED + [COUNTER]


def test_a_trigger_variable_that_does_not_resolve_is_a_failed_object():
    bench = bench_with(values=plc_fakes.VALUES)
    result = bench.run(trigger_job())
    assert not result["ok"]
    assert result["data"]["failed_objects"] == [COUNTER]
    assert bench.calls("download") == []


def test_a_bool_trigger_is_refused():
    bench = bench_with()
    result = bench.run(trigger_job(variable=PULSE))
    assert not result["ok"]
    assert "%s is the trigger" % PULSE in result["summary"]
    assert "numeric" in result["summary"]
    assert result["data"]["failed_objects"] == [PULSE]
    assert bench.calls("download", "start") == []


# --------------------------------------------------------------------------
# Record condition
# --------------------------------------------------------------------------

def condition_job():
    return plc_fakes.trace_job(record_condition=PULSE)


def test_a_condition_is_set_and_its_run_is_not_judged_for_completeness():
    # The gapped file would fail a plain run; under a condition, gaps are
    # the condition working.
    bench = bench_with(csv_text=plc_fakes.gapped_csv())
    result = bench.run(condition_job())
    assert result["ok"], result["summary"]
    assert bench.tracer.api.record_condition == PULSE
    data = result["data"]
    assert data["complete"] is None and "trigger" not in data
    row = data["variables"][0]
    assert set(row) == {"name", "type", "samples", "expected", "complete",
                        "gaps", "longest_interval"}
    assert (row["expected"], row["complete"], row["gaps"]) == (None,) * 3
    assert row["samples"] > 0 and row["longest_interval"] > 0
    assert "completeness is not judged" in result["summary"]


def test_a_condition_run_with_no_variables_in_its_file_still_fails():
    header = u"".join(line for line in plc_fakes.read_data(
        plc_fakes.SAMPLE_CSV).splitlines(True) if u"Variable" not in line
        and not line.startswith(u";") and not line[:1].isdigit())
    result = bench_with(csv_text=header).run(condition_job())
    assert not result["ok"] and "no variables" in result["summary"]


def test_a_condition_that_is_not_a_bool_is_refused_by_name():
    bench = bench_with()
    result = bench.run(plc_fakes.trace_job(record_condition=COUNTER))
    assert not result["ok"]
    assert "%s is the record_condition" % COUNTER in result["summary"]
    assert "not a BOOL" in result["summary"]
    assert result["data"]["failed_objects"] == [COUNTER]
    assert bench.calls("download", "start") == []


def test_a_condition_with_a_judging_field_is_refused_before_anything():
    bench = bench_with()
    job = dict(condition_job(), min_complete=0.5)
    result = bench.run(job)
    assert not result["ok"]
    assert "cannot be given with record_condition" in result["summary"]
    assert bench.tracer.created == []
