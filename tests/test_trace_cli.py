# -*- coding: utf-8 -*-
"""`plc trace` from outside the IDE: the flags, the job file, the result.

Everything the CLI decides before an IDE starts (SPEC 6.8: a wrong job is
refused before any IDE starts, and a missing --gateway is exit 2), what the
IDE side is handed, and what a trace's result record prints and exits with.
How long the launch waits for a trace is test_headless_cli.py's.
"""
import json
import os

import pytest

from cds.core import commands, trace_job
from cds.core.exits import EXIT_DENIED, EXIT_FAILED, EXIT_OK
from cds.ide import permit
from cdsint import cli

GOOD = {"task": "MainTask", "variables": ["PRG_X.var"], "duration_s": 3,
        "out": "out/run1"}


def write_job(folder, job):
    path = folder / "job.json"
    path.write_text(job if isinstance(job, str) else json.dumps(job),
                    encoding="utf-8")
    return str(path)


def trace_argv(job_path, *more):
    return (["plc", "trace", "--project", "P", "--install", "I",
             "--gateway", "192.168.1.5", "--job", job_path] + list(more))


class Runner(object):
    """Answers with one record, and remembers the steps it was handed."""

    def __init__(self, result):
        self.result = result
        self.asked = None

    def describe(self):
        return "a fake IDE"

    def sync_dir(self):
        return None

    def run(self, steps):
        self.asked = steps
        return [dict(self.result, command=steps[0][0])]


@pytest.fixture
def runner(monkeypatch):
    made = Runner(traced(True))
    started = []

    def make_runner(ns):
        started.append(ns)
        return made

    monkeypatch.setattr(cli, "make_runner", make_runner)
    made.started = started
    return made


def traced(ok, **rest):
    data = {"action": "trace", "crc": "MATCH", "complete": ok,
            "files": {"csv": "C:/t/out.csv", "trace": "C:/t/out.trace"},
            "variables": [{"name": "PRG_X.var", "type": "INT",
                           "samples": 745, "expected": 750,
                           "complete": 0.99333, "gaps": [[10, 30]],
                           "longest_interval": 20}],
            "failed_objects": [], "why": None}
    return commands.new_result(commands.new_command("plc trace"), ok,
                               data=data, **rest)


def refused(argv, capsys):
    with pytest.raises(SystemExit) as raised:
        cli.main(argv)
    assert raised.value.code == 2
    return capsys.readouterr().err


# --- the flags ---------------------------------------------------------------

def test_a_trace_without_a_gateway_is_refused_with_the_reason(
        tmp_path, runner, capsys):
    said = refused(["plc", "trace", "--project", "P", "--install", "I",
                    "--job", write_job(tmp_path, GOOD)], capsys)
    assert "needs --gateway" in said and "wrong controller" in said
    assert not runner.started


def test_a_trace_without_a_job_is_refused(runner, capsys):
    said = refused(["plc", "trace", "--project", "P", "--install", "I",
                    "--gateway", "192.168.1.5"], capsys)
    assert "needs --job" in said
    assert not runner.started


@pytest.mark.parametrize("action", ["connect", "download"])
def test_only_a_trace_takes_a_job(action, tmp_path, runner, capsys):
    said = refused(["plc", action, "--project", "P", "--install", "I",
                    "--job", write_job(tmp_path, GOOD)], capsys)
    assert "does not take --job" in said
    assert not runner.started


# --- the job file ------------------------------------------------------------

@pytest.mark.parametrize("job, named", [
    ('{"task": ', "not JSON"),
    (dict(GOOD, colour="red"), '"colour"'),
    (dict(GOOD, duration_s="3"), "duration_s"),
    (dict((k, v) for k, v in GOOD.items() if k != "task"), "task"),
])
def test_a_bad_job_is_refused_before_any_ide_starts(job, named, tmp_path,
                                                    runner, capsys):
    path = write_job(tmp_path, job)
    said = refused(trace_argv(path), capsys)
    assert os.path.abspath(path) in said and named in said
    assert not runner.started


def test_a_job_file_that_is_not_there_is_refused(tmp_path, runner, capsys):
    path = str(tmp_path / "nope.json")
    said = refused(trace_argv(path), capsys)
    assert path in said and "cannot read" in said
    assert not runner.started


def test_a_refusal_lists_the_fields_from_the_one_table(tmp_path, runner,
                                                       capsys):
    said = refused(trace_argv(write_job(tmp_path, dict(GOOD, x=1))), capsys)
    for line in trace_job.table():
        assert line.strip() in said


def test_the_ide_side_is_handed_the_job_not_the_file(tmp_path, runner,
                                                     monkeypatch):
    # The IDE's working directory is not the shell's, so a relative `out`
    # has to be resolved here, against the directory the caller typed in.
    monkeypatch.chdir(tmp_path)
    path = write_job(tmp_path, GOOD)
    bom = tmp_path / "bom.json"
    bom.write_bytes(b"\xef\xbb\xbf" + json.dumps(GOOD).encode("utf-8"))
    for given in (path, str(bom)):
        assert cli.main(trace_argv(given)) == EXIT_OK
        command, args = runner.asked[0]
        expected, _problem = trace_job.normalise(GOOD)
        expected["out"] = str(tmp_path / "out" / "run1")
        assert command == "plc trace"
        assert args == {"yes": None, "gateway": "192.168.1.5", "port": None,
                        "job": expected}


# --- what comes back ---------------------------------------------------------

def test_a_trace_result_prints_what_decides_whether_to_trust_it(
        tmp_path, runner, capsys):
    cli.main(trace_argv(write_job(tmp_path, GOOD)))
    out = capsys.readouterr().out
    assert "MATCH" in out and "complete" in out
    assert "PRG_X.var  745/750 samples  complete 0.9933  gaps 1" in out
    assert "C:/t/out.csv" in out and "C:/t/out.trace" in out


def test_a_condition_row_prints_what_it_has(tmp_path, runner, capsys):
    # SPEC 6.8: under a record_condition nothing says how many samples there
    # should have been, so the row carries no expected, complete or gaps.
    record = traced(True)
    record["data"].update(complete=None, variables=[
        {"name": "PRG_X.var", "type": "INT", "samples": 27, "expected": None,
         "complete": None, "gaps": None, "longest_interval": 500000}])
    runner.result = record
    assert cli.main(trace_argv(write_job(tmp_path, GOOD))) == EXIT_OK
    out = capsys.readouterr().out
    assert "PRG_X.var  27 samples  longest interval 500000" in out


def test_a_trace_result_under_json_is_the_record(tmp_path, runner, capsys):
    cli.main(trace_argv(write_job(tmp_path, GOOD), "--json"))
    printed = json.loads(capsys.readouterr().out)
    assert printed["data"]["variables"][0]["gaps"] == [[10, 30]]


@pytest.mark.parametrize("result, code", [
    (traced(True), EXIT_OK),
    # Incomplete samples: it ran and did not work (SPEC 6.8).
    (traced(False, error="PRG_X.var is 0.9 complete"), EXIT_FAILED),
    (traced(False, error="not allowed",
            denied=permit.record(None, "trace")), EXIT_DENIED),
])
def test_a_trace_exits_the_way_every_plc_command_does(result, code, tmp_path,
                                                      runner):
    runner.result = result
    assert cli.main(trace_argv(write_job(tmp_path, GOOD))) == code


def test_the_reference_job_table_is_the_one_a_refusal_prints():
    # docs/REFERENCE.md carries a copy so a reader can see the fields without
    # making a mistake first; this keeps the copy from being a second source.
    reference = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "docs", "REFERENCE.md")
    with open(reference, encoding="utf-8") as handle:
        text = handle.read()
    first = trace_job.table()[0]
    assert first in text, "REFERENCE.md has no job table"
    # The whole fenced block, so a field dropped from the code cannot live on
    # in the reference either.
    block = text[text.index(first):].split("```")[0]
    assert block.splitlines() == trace_job.table()
