# -*- coding: utf-8 -*-
"""A job read as a definition alone: what to record, not how long or where.

`trace job` writes the definition a trace object holds, which has no
duration_s and no out, and `trace apply` has to take that file back -- and a
full `plc trace` job too, since an agent may apply the job it records with.
"""
from cds.core import trace_job

FULL = {"task": "MainTask", "variables": ["PLC_PRG.n"], "duration_s": 5,
        "out": "o"}


def test_a_definition_needs_no_run_keys():
    definition, problem = trace_job.normalise_definition(
        {"task": "MainTask", "variables": ["PLC_PRG.n"]})
    assert problem is None
    assert definition == {"task": "MainTask", "variables": ["PLC_PRG.n"],
                          "resolution": "us", "every_n_cycles": 1}


def test_run_keys_are_checked_then_dropped():
    definition, problem = trace_job.normalise_definition(FULL)
    assert problem is None
    assert "duration_s" not in definition and "out" not in definition
    _, problem = trace_job.normalise_definition(dict(FULL, duration_s=-1))
    assert "duration_s" in problem


def test_the_combination_rules_still_hold():
    _, problem = trace_job.normalise_definition(dict(
        FULL, record_condition="PLC_PRG.b",
        trigger={"variable": "PLC_PRG.n", "edge": "rising", "level": 1,
                 "post_samples": 1}))
    assert "together" in problem


def test_a_definition_keeps_its_trigger():
    trigger = {"variable": "PLC_PRG.n", "edge": "falling", "level": 3,
               "post_samples": 10}
    definition, problem = trace_job.normalise_definition(
        {"task": "MainTask", "variables": ["PLC_PRG.n"], "trigger": trigger})
    assert problem is None and definition["trigger"] == trigger


def test_a_run_job_still_needs_its_run_keys():
    _, problem = trace_job.normalise({"task": "T", "variables": ["a.b"]})
    assert "duration_s is required" in problem


def test_a_definition_with_a_record_condition():
    definition, problem = trace_job.normalise_definition(
        {"task": "MainTask", "variables": ["PLC_PRG.n"],
         "record_condition": "PLC_PRG.b"})
    assert problem is None
    assert definition["record_condition"] == "PLC_PRG.b"
