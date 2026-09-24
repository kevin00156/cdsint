# -*- coding: utf-8 -*-
"""The `plc trace` job file's schema: its fields, and what refuses what.

The job file is written by hand, so every refusal is a promise to the person
who wrote it (SPEC 6.8): it names the field, what was there, and what is
allowed. The buffers a job implies are tests/test_trace_run.py's.
"""
import io
import os
import re

import pytest

from cds.core import trace_job

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(REPO_ROOT, "docs", "SPEC.md")

MINIMAL = {"task": "MainTask", "variables": ["PRG_X.a", "GVL.b"],
           "duration_s": 3, "out": "out/run"}


def job(**changes):
    found = dict(MINIMAL)
    found.update(changes)
    return found


def refused(found):
    value, problem = trace_job.normalise(found)
    assert value is None
    return problem


def documented():
    """Every field name in SPEC 6.8's job-file table."""
    with io.open(SPEC, encoding="utf-8") as handle:
        text = handle.read()
    section = text.split("**The job file.**", 1)[1].split("**Completeness.**")[0]
    return set(re.findall(r"^\| `([a-z_]+)` \|", section, re.MULTILINE))


def test_the_code_and_the_spec_name_the_same_fields():
    assert set(trace_job.KINDS) == documented()


def test_a_minimal_job_gets_every_default():
    value, problem = trace_job.normalise(MINIMAL)
    assert problem is None
    assert value == {"task": "MainTask", "variables": ["PRG_X.a", "GVL.b"],
                     "duration_s": 3.0, "out": "out/run",
                     "formats": ["trace", "csv"], "resolution": "us",
                     "every_n_cycles": 1, "min_complete": 0.99,
                     "max_gap_periods": 20}


def test_the_default_formats_are_not_shared_between_jobs():
    first, _ = trace_job.normalise(MINIMAL)
    first["formats"].append("txt")
    second, _ = trace_job.normalise(MINIMAL)
    assert second["formats"] == ["trace", "csv"]


def test_every_optional_field_is_kept_as_written():
    value, problem = trace_job.normalise(job(
        formats=["txt"], resolution="ms", every_n_cycles=4,
        min_complete=1, max_gap_periods=3, duration_s=0.5))
    assert problem is None
    assert (value["formats"], value["resolution"], value["every_n_cycles"],
            value["min_complete"], value["max_gap_periods"],
            value["duration_s"]) == (["txt"], "ms", 4, 1.0, 3, 0.5)


def test_a_job_that_is_not_an_object_is_refused():
    assert "not a JSON object" in refused(["MainTask"])


def test_an_unknown_field_is_refused_with_the_known_ones_listed():
    problem = refused(job(triggr="x"))
    assert '"triggr" is not a job field' in problem
    for name in trace_job.KINDS:
        assert name in problem


@pytest.mark.parametrize("name", ["task", "variables", "duration_s", "out"])
def test_each_required_field_is_refused_when_missing(name):
    found = dict(MINIMAL)
    del found[name]
    assert "%s is required and missing" % name in refused(found)


@pytest.mark.parametrize("name, value, words", [
    ("task", "", "task wants a non-empty string"),
    ("task", "   ", "task wants a non-empty string"),
    ("task", 3, "not 3"),
    ("out", None, "out wants a non-empty string, not null"),
    ("duration_s", 0, "duration_s wants a number greater than 0, not 0"),
    ("duration_s", -1.5, "not -1.5"),
    ("duration_s", "3", 'not "3"'),
    ("duration_s", True, "not true"),
    ("every_n_cycles", 0, "every_n_cycles wants a whole number"),
    ("every_n_cycles", 1.5, "not 1.5"),
    ("every_n_cycles", True, "not true"),
    ("max_gap_periods", 0, "max_gap_periods wants a whole number"),
    ("min_complete", 1.01, "min_complete wants a number from 0 to 1"),
    ("min_complete", -0.1, "not -0.1"),
    ("min_complete", False, "not false"),
    ("resolution", "s", 'resolution wants either "us" or "ms", not "s"'),
    ("resolution", "US", 'not "US"'),
])
def test_a_scalar_of_the_wrong_shape_names_field_value_and_kind(
        name, value, words):
    assert words in refused(job(**{name: value}))


@pytest.mark.parametrize("value, words", [
    ([], "not []"),
    ("PRG_X.a", 'not "PRG_X.a"'),
    (["PRG_X.a", ""], '("" is not a variable path)'),
    (["PRG_X.a", 7], "(7 is not a variable path)"),
    (["PRG_X.a", "PRG_X.a"], '("PRG_X.a" appears twice)'),
    (["PRG_X.a", "prg_x.A"], '("prg_x.A" appears twice)'),
    (["Application.PRG_X.a"], "carries the application prefix"),
])
def test_a_bad_variable_list_says_which_element(value, words):
    problem = refused(job(variables=value))
    assert "variables wants a non-empty list" in problem
    assert words in problem


@pytest.mark.parametrize("value, words", [
    ([], "not []"),
    (["xml"], '("xml" is not one of trace, csv, txt)'),
    (["csv", "csv"], '("csv" appears twice)'),
    ("csv", 'not "csv"'),
])
def test_a_bad_format_list_says_which_element(value, words):
    problem = refused(job(formats=value))
    assert "formats wants a non-empty list" in problem
    assert words in problem


def test_every_refusal_carries_the_table():
    problem = refused(job(duration_s=0))
    assert "The job fields:" in problem
    assert "default 0.99" in problem
    assert "every_n_cycles" in problem


def test_the_table_marks_the_required_fields():
    lines = dict((line.split()[0], line) for line in trace_job.table())
    assert "required" in lines["task"]
    assert 'default ["trace", "csv"]' in lines["formats"]


def test_the_table_marks_the_optional_fields():
    lines = dict((line.split()[0], line) for line in trace_job.table())
    assert "; optional." in lines["trigger"]
    assert "; optional." in lines["record_condition"]


# -- trigger and record_condition -------------------------------------------

TRIGGER = {"variable": "GVL.udiCount", "edge": "rising", "level": 5000,
           "post_samples": 2000}


def trigger(**changes):
    found = dict(TRIGGER)
    found.update(changes)
    return found


def test_a_trigger_is_kept_as_written():
    value, problem = trace_job.normalise(job(trigger=TRIGGER))
    assert problem is None
    assert value["trigger"] == TRIGGER
    # a trigger does not change what completeness is judged by
    assert value["min_complete"] == 0.99 and value["max_gap_periods"] == 20


def test_a_float_level_is_a_number_too():
    value, _ = trace_job.normalise(job(trigger=trigger(level=12.5)))
    assert value["trigger"]["level"] == 12.5


@pytest.mark.parametrize("value, words", [
    ("x", 'not "x"'),
    ([TRIGGER], "trigger wants an object"),
    (trigger(when="now"), '("when" is not a trigger key)'),
    (dict((k, v) for k, v in TRIGGER.items() if k != "edge"),
     "(edge is missing)"),
    (trigger(edge="up"), '(edge "up" is not one of rising, falling, both)'),
    (trigger(edge="Positive"), '(edge "Positive" is not one of'),
    (trigger(level=True), "(level true is not a number)"),
    (trigger(level="5000"), '(level "5000" is not a number)'),
    (trigger(post_samples=0), "(post_samples 0 is not a whole number"),
    (trigger(post_samples=2.5), "(post_samples 2.5 is not a whole number"),
    (trigger(variable=""), '(variable "" is not a variable path)'),
    (trigger(variable="Application.GVL.x"),
     "carries the application prefix"),
    (trigger(variable="GVL.a + 1"), "is not a single variable path"),
])
def test_a_bad_trigger_says_which_key(value, words):
    problem = refused(job(trigger=value))
    assert "trigger wants an object" in problem
    assert words in problem


def test_a_condition_is_kept_and_completeness_is_not_judged():
    value, problem = trace_job.normalise(job(record_condition="GVL.xPulse"))
    assert problem is None
    assert value["record_condition"] == "GVL.xPulse"
    assert "min_complete" not in value and "max_gap_periods" not in value


@pytest.mark.parametrize("value", [
    "udiProbeCnt MOD 2 = 0", "GVL.a AND GVL.b", "NOT GVL.x", "GVL.a<GVL.b",
    "", 3, ["GVL.x"]])
def test_a_condition_that_is_not_one_variable_is_refused(value):
    assert "record_condition wants one variable path" in refused(
        job(record_condition=value))


def test_an_indexed_path_is_one_variable():
    value, problem = trace_job.normalise(
        job(record_condition="PRG_X.axFlags[3]"))
    assert problem is None


@pytest.mark.parametrize("given", [{"min_complete": 0.5},
                                   {"max_gap_periods": 3},
                                   {"min_complete": 0.99}])
def test_a_judging_field_beside_a_condition_is_refused(given):
    # Even the default value: it was written, so somebody expects it to act.
    problem = refused(job(record_condition="GVL.x", **given))
    assert "cannot be given with record_condition" in problem
    assert list(given)[0] in problem


def test_trigger_and_condition_together_are_refused():
    problem = refused(job(trigger=TRIGGER, record_condition="GVL.x"))
    assert "trigger and record_condition cannot be given together" in problem


@pytest.mark.parametrize("extra", [
    {}, {"trigger": TRIGGER}, {"record_condition": "GVL.x"},
    {"formats": ["txt"], "min_complete": 1}])
def test_a_normalised_job_normalises_to_itself(extra):
    # The engine checks again what the CLI already normalised (SPEC 6.8).
    first, problem = trace_job.normalise(job(**extra))
    assert problem is None
    assert trace_job.normalise(first) == (first, None)


def test_named_reads_every_name_once_recorded_first():
    found, _ = trace_job.normalise(job(trigger=trigger(variable="gvl.B")))
    assert trace_job.named(found) == ["PRG_X.a", "GVL.b"]
    found, _ = trace_job.normalise(job(trigger=TRIGGER))
    assert trace_job.named(found) == ["PRG_X.a", "GVL.b", "GVL.udiCount"]
    found, _ = trace_job.normalise(job(record_condition="GVL.x"))
    assert trace_job.named(found) == ["PRG_X.a", "GVL.b", "GVL.x"]
