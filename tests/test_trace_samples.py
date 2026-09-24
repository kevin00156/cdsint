# -*- coding: utf-8 -*-
"""Reading a saved trace CSV, and the completeness verdict on its samples.

The verdict is what `plc trace` exits on (SPEC 6.8): a hole the size of the
IDE's fetch interval is lost data and fails the run; the few-period gaps a
non-realtime controller leaves are reported and pass. The fixture is the head
of a real `save()` from the bench, two variables on a 1 ms task, in
microseconds.
"""
import io
import os

import pytest

from cds.core import trace_samples

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                       "trace_sample.csv")

HEADER = (u"[key]; [value]\n"
          u"IecTaskName; MainTask\n"
          u"EveryNCycles; 1\n"
          u"BufferEntries; 5000\n"
          u"Flags; %s\n")


def write_csv(tmp_path, variables, flags="32", bom=False):
    """A CSV in save()'s shape: {name: [(timestamp, value), ...]}."""
    lines = [HEADER % flags]
    for index, (name, rows) in enumerate(variables):
        lines.append(u"%d.Variable; %s\n%d.Class; 7\n%d.Data; \n"
                     % (index, name, index, index))
        lines.extend(u"; %d; %s\r\n" % row for row in rows)
    path = os.path.join(str(tmp_path), "run.csv")
    with io.open(path, "w", encoding="utf-8-sig" if bom else "utf-8",
                 newline="") as handle:
        handle.write(u"".join(lines))
    return path


def steady(count, period, start=0, value=u"0"):
    return [(start + index * period, value) for index in range(count)]


def test_the_bench_file_header():
    header = trace_samples.read_csv(FIXTURE)["header"]
    assert header["IecTaskName"] == "EtherCAT_Task"
    assert header["BufferEntries"] == "5000"
    assert header["EveryNCycles"] == "1"
    assert trace_samples.file_unit(header) == "us"


def test_the_bench_file_variables():
    variables = trace_samples.read_csv(FIXTURE)["variables"]
    assert [v["name"] for v in variables] == [
        "PRG_AxisControl._uFlags", "PRG_AxisControl._iOvrZone"]
    first, second = variables
    assert (len(first["timestamps"]), first["timestamps"][:3],
            first["timestamps"][-1]) == (21, [291, 1257, 2254], 20207)
    assert len(second["timestamps"]) == 20
    assert set(second["values"]) == set(["3"])


def test_the_bench_file_is_complete_at_one_ms():
    variables = trace_samples.read_csv(FIXTURE)["variables"]
    rows, complete = trace_samples.judge(variables, 1000, 0.99, 20)
    assert complete
    assert rows[0] == {"name": "PRG_AxisControl._uFlags", "samples": 21,
                       "expected": 20, "complete": 1.05, "gaps": [],
                       "longest_interval": 1136}


def test_a_bom_and_crlf_line_ends_read_the_same(tmp_path):
    path = write_csv(tmp_path, [("GVL.a", steady(3, 1000))], bom=True)
    found = trace_samples.read_csv(path)
    assert found["header"]["Flags"] == "32"
    assert found["variables"] == [{"name": "GVL.a",
                                   "timestamps": [0, 1000, 2000],
                                   "values": ["0", "0", "0"]}]


def test_a_value_keeps_everything_after_the_timestamp(tmp_path):
    path = write_csv(tmp_path, [("GVL.s", [(0, u"a; b")])])
    assert trace_samples.read_csv(path)["variables"][0]["values"] == ["a; b"]


@pytest.mark.parametrize("text, words", [
    (u"; 5; 0\n", "line 1 is a sample before any variable"),
    (u"0.Variable; GVL.a\n; x; 0\n", "line 2 has no whole-number timestamp"),
    (u"0.Variable; GVL.a\n;\n", "line 2 has no whole-number timestamp"),
    (u"garbage\n", "line 1 is not 'key; value'"),
    (u"0.Variable; GVL.a\nFlags; 32\n", "line 2 is neither a sample nor"),
])
def test_a_file_not_in_saves_shape_is_refused_by_line(tmp_path, text, words):
    path = os.path.join(str(tmp_path), "bad.csv")
    with io.open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    with pytest.raises(trace_samples.Unreadable) as caught:
        trace_samples.read_csv(path)
    assert words in str(caught.value)


@pytest.mark.parametrize("flags, unit", [
    ("32", "us"), ("16", "ms"), ("0", None), ("", None),
    # a record condition sets bit 4 as well (research 13.4)
    ("36", "us"), ("20", "ms"), ("48", None), ("x", None)])
def test_the_unit_comes_from_flags(flags, unit):
    assert trace_samples.file_unit({"Flags": flags}) == unit


def test_no_flags_line_is_no_unit():
    assert trace_samples.file_unit({}) is None


def test_periods_in_the_files_unit():
    assert trace_samples.to_file_units(4000, "us") == 4000
    assert trace_samples.to_file_units(4000, "ms") == 4
    assert trace_samples.to_file_units(500, "ms") == 0.5


def test_one_complete_variable_and_one_with_an_eighty_period_hole(tmp_path):
    # The second variable loses 80 samples in the middle: the shape a ring
    # buffer overflow leaves (docs/trace-research.md 2.1).
    holed = steady(100, 1000) + steady(120, 1000, start=180000)
    path = write_csv(tmp_path, [("GVL.ok", steady(300, 1000)),
                                ("GVL.holed", holed)])
    variables = trace_samples.read_csv(path)["variables"]
    rows, complete = trace_samples.judge(variables, 1000, 0.99, 20)
    assert not complete
    assert rows[0] == {"name": "GVL.ok", "samples": 300, "expected": 300,
                       "complete": 1.0, "gaps": [], "longest_interval": 1000}
    assert rows[1] == {"name": "GVL.holed", "samples": 220, "expected": 300,
                       "complete": 0.7333, "gaps": [[99000, 180000]],
                       "longest_interval": 81000}


def test_jitter_is_listed_but_passes():
    # Three missed cycles on a long run: listed, not failed.
    stamps = list(range(0, 1000, 1)) + [1003] + list(range(1004, 2000, 1))
    variables = [{"name": "v", "timestamps": stamps, "values": []}]
    rows, complete = trace_samples.judge(variables, 1, 0.99, 20)
    assert complete
    assert rows[0]["gaps"] == [[999, 1003]]
    assert rows[0]["longest_interval"] == 4


def test_a_gap_just_over_the_limit_fails_even_when_the_count_is_fine():
    stamps = list(range(0, 5000)) + list(range(5020, 10000))
    rows, complete = trace_samples.judge(
        [{"name": "v", "timestamps": stamps, "values": []}], 1, 0.99, 20)
    assert rows[0]["complete"] >= 0.99
    assert not complete


def test_a_gap_of_exactly_the_limit_passes():
    stamps = list(range(0, 5000)) + list(range(5019, 10000))
    _, complete = trace_samples.judge(
        [{"name": "v", "timestamps": stamps, "values": []}], 1, 0.99, 20)
    assert complete


def test_one_and_a_half_periods_is_not_yet_a_gap():
    # Period 2: an interval of 3 is exactly 1.5 periods, 4 is past it.
    rows, _ = trace_samples.judge(
        [{"name": "v", "timestamps": [0, 3, 7], "values": []}], 2, 0, 20)
    assert rows[0]["gaps"] == [[3, 7]]


def test_completeness_is_rounded_to_four_places():
    stamps = [0, 1, 2, 4, 5, 6]          # 6 of 7
    rows, _ = trace_samples.judge(
        [{"name": "v", "timestamps": stamps, "values": []}], 1, 0.99, 20)
    assert rows[0]["complete"] == 0.8571


def test_a_task_that_ran_faster_reports_more_than_one():
    rows, _ = trace_samples.judge(
        [{"name": "v", "timestamps": [0, 1, 2, 3], "values": []}], 2, 0.99, 20)
    assert (rows[0]["expected"], rows[0]["complete"]) == (2, 2.0)


def test_a_variable_with_no_samples_is_zero_and_fails():
    rows, complete = trace_samples.judge(
        [{"name": "v", "timestamps": [], "values": []}], 1000, 0.99, 20)
    assert rows[0] == {"name": "v", "samples": 0, "expected": 0,
                       "complete": 0.0, "gaps": [], "longest_interval": 0}
    assert not complete


def test_one_sample_is_complete_with_no_interval():
    rows, complete = trace_samples.judge(
        [{"name": "v", "timestamps": [42], "values": []}], 1000, 0.99, 20)
    assert (rows[0]["expected"], rows[0]["complete"],
            rows[0]["longest_interval"]) == (1, 1.0, 0)
    assert complete


def test_nothing_recorded_is_not_complete():
    assert trace_samples.judge([], 1000, 0.99, 20) == ([], False)


# -- samples under a record condition ----------------------------------------

def test_counted_rows_carry_samples_and_the_longest_interval_only():
    # research 13.4: TRUE every 500 cycles, so every interval is 500 periods,
    # and that is the condition working, not a gap.
    variables = [{"name": u"GVL.x", "timestamps": [0, 500, 1000, 1600],
                  "values": [u"1"] * 4}]
    assert trace_samples.counted(variables) == [
        {"name": u"GVL.x", "samples": 4, "expected": None, "complete": None,
         "gaps": None, "longest_interval": 600}]


def test_a_condition_that_never_held_counts_zero():
    rows = trace_samples.counted([{"name": u"GVL.x", "timestamps": [],
                                   "values": []}])
    assert rows[0]["samples"] == 0 and rows[0]["longest_interval"] == 0
