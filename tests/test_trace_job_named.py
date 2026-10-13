# -*- coding: utf-8 -*-
"""The job of plc trace --name: only how long to record and where to write.

What to record is the named trace object's (SPEC 6.8), so a definition key
in the job would be a second answer to the same question.
"""
import argparse
import json

import pytest

from cds.core import trace_job
from cdsint import job_file

RUN = {"duration_s": 5, "out": "C:/runs/t1"}


def test_a_named_job_needs_no_definition():
    job, problem = trace_job.normalise(RUN, named=True)
    assert problem is None
    assert job == RUN


@pytest.mark.parametrize("key", trace_job.DEFINITION_KEYS)
def test_a_named_job_refuses_every_definition_key(key):
    problem = trace_job.normalise(dict(RUN, **{key: "x"}), named=True)[1]
    assert key in problem and "trace apply" in problem


def test_a_named_job_still_needs_its_run():
    problem = trace_job.normalise({"out": "x"}, named=True)[1]
    assert "duration_s is required" in problem


def test_a_named_job_fills_no_defaults():
    # The definition comes later, from the trace; a min_complete filled in
    # here would then sit beside the trace's record_condition and be refused
    # as if the person had written it.
    job, _problem = trace_job.normalise(RUN, named=True)
    assert "formats" not in job and "min_complete" not in job


def test_a_named_job_merged_with_a_conditioned_trace_normalises():
    run, _problem = trace_job.normalise(RUN, named=True)
    merged = dict({"task": "MainTask", "variables": ["a.x"],
                   "record_condition": "a.b"}, **run)
    job, problem = trace_job.normalise(merged)
    assert problem is None and job["formats"] == ["trace", "csv"]


def test_a_named_job_normalises_again_to_itself():
    # The engine checks what the CLI already checked (SPEC 6.8).
    run, _problem = trace_job.normalise(dict(RUN, formats=["csv"]),
                                        named=True)
    assert trace_job.normalise(run, named=True) == (run, None)


def write(tmp_path, job):
    path = tmp_path / "run.json"
    path.write_text(json.dumps(job), encoding="utf-8")
    return str(path)


def test_checked_reads_a_named_job_and_makes_out_absolute(tmp_path):
    loaded = job_file.load(write(tmp_path, {"duration_s": 2, "out": "o"}))
    job = job_file.checked(loaded, named=True)
    assert job["out"].endswith("o") and job["out"] != "o"


def test_checked_refuses_a_definition_in_a_named_job(tmp_path):
    loaded = job_file.load(write(tmp_path, {"duration_s": 2, "out": "o",
                                            "task": "T"}))
    with pytest.raises(argparse.ArgumentTypeError) as caught:
        job_file.checked(loaded, named=True)
    assert "run.json" in str(caught.value)


def test_checked_unnamed_is_the_whole_job_as_before(tmp_path):
    loaded = job_file.load(write(tmp_path, {"duration_s": 2, "out": "o",
                                            "task": "T",
                                            "variables": ["a"]}))
    assert job_file.checked(loaded, named=False)["formats"] == ["trace",
                                                                 "csv"]


def test_waits_s_is_the_jobs_duration_or_nothing():
    assert job_file.waits_s({"job": {"duration_s": 3.5}}) == 3.5
    assert job_file.waits_s({"job": None}) == 0.0
    assert job_file.waits_s({}) == 0.0
