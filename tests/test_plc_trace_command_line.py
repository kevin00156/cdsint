# -*- coding: utf-8 -*-
"""What `cdsint plc trace` looks like in each of its two forms.

The watcher form records a trace object the caller names, through the login
already open in that IDE, so it needs --name and refuses --gateway; the
--project form logs in itself and needs --gateway. --stop ends a watcher's
recording and takes nothing else. connect and download keep their one form
(SPEC D8).
"""
import json

import pytest

from cdsint import flags, refusals, target

PROJECT = ["--project", "p.project", "--install", "3.5.21.40"]


def parse(argv):
    parser = flags.build_parser()
    ns = parser.parse_args(argv)
    refusals.check(parser, ns)
    return ns


def refused(argv, capsys):
    with pytest.raises(SystemExit) as stopped:
        parse(argv)
    assert stopped.value.code == 2
    return capsys.readouterr().err


def write_job(tmp_path, job):
    path = tmp_path / "run.json"
    path.write_text(json.dumps(job), encoding="utf-8")
    return str(path)


RUN = {"duration_s": 2, "out": "o"}
WHOLE = {"duration_s": 2, "out": "o", "task": "T", "variables": ["a"]}


def test_the_watcher_form_takes_a_name_and_a_run_only_job(tmp_path):
    ns = parse(["plc", "trace", "--target", "softplc", "--name", "T1",
                "--job", write_job(tmp_path, RUN)])
    assert ns.job["duration_s"] == 2 and "task" not in ns.job
    assert flags.wire_name(ns) == "plc trace"


def test_the_watcher_form_needs_a_name(tmp_path, capsys):
    err = refused(["plc", "trace", "--target", "softplc",
                   "--job", write_job(tmp_path, WHOLE)], capsys)
    assert "needs --name" in err and "logged in" in err


def test_the_watcher_form_refuses_a_gateway(tmp_path, capsys):
    err = refused(["plc", "trace", "--target", "softplc", "--name", "T1",
                   "--job", write_job(tmp_path, RUN),
                   "--gateway", "127.0.0.1"], capsys)
    assert "does not take --gateway" in err and "login" in err


def test_a_named_job_with_a_definition_is_refused_at_the_parser(tmp_path,
                                                                capsys):
    err = refused(["plc", "trace", "--target", "softplc", "--name", "T1",
                   "--job", write_job(tmp_path, dict(RUN, task="T"))],
                  capsys)
    assert "trace apply" in err and "run.json" in err


def test_an_unnamed_job_still_needs_its_definition(tmp_path, capsys):
    err = refused(["plc", "trace"] + PROJECT +
                  ["--gateway", "1.2.3.4", "--job", write_job(tmp_path, RUN)],
                  capsys)
    assert "task is required" in err


def test_stop_stands_alone(capsys):
    ns = parse(["plc", "trace", "--target", "softplc", "--stop"])
    assert ns.stop is True and ns.job is None
    err = refused(["plc", "trace", "--target", "softplc", "--stop",
                   "--name", "T1"], capsys)
    assert "plc trace --stop does not take --name" in err


def test_stop_is_the_watchers_only(capsys):
    err = refused(["plc", "trace"] + PROJECT + ["--stop"], capsys)
    assert "does not take --stop" in err and "watcher" in err


@pytest.mark.parametrize("action", ["connect", "download"])
def test_connect_and_download_keep_the_project_form_only(action, capsys):
    err = refused(["plc", action, "--target", "softplc", "--gateway",
                   "1.2.3.4"], capsys)
    assert "no --target form" in err and "D8" in err


@pytest.mark.parametrize("flag", [["--name", "T1"], ["--stop"]])
def test_connect_takes_neither_name_nor_stop(flag, capsys):
    err = refused(["plc", "connect"] + PROJECT + ["--gateway", "1.2.3.4"]
                  + flag, capsys)
    assert "Only plc trace takes it" in err


def test_the_project_form_still_needs_a_gateway(tmp_path, capsys):
    err = refused(["plc", "trace"] + PROJECT +
                  ["--job", write_job(tmp_path, WHOLE)], capsys)
    assert "needs --gateway" in err


def test_the_project_form_takes_a_name_with_a_run_only_job(tmp_path):
    ns = parse(["plc", "trace"] + PROJECT +
               ["--gateway", "1.2.3.4", "--name", "T1",
                "--job", write_job(tmp_path, RUN)])
    assert ns.name == "T1" and "task" not in ns.job


def test_a_recording_is_waited_for_on_top_of_the_timeout(monkeypatch):
    seen = {}

    def send(root, instance_id, cmd, timeout):
        seen["timeout"] = timeout
        return {"ok": True}
    monkeypatch.setattr(target, "send", send)
    picked = object.__new__(target.Target)
    picked.root, picked.instance_id, picked.timeout = "r", "i", 10.0
    picked.run_one("plc trace", {"job": {"duration_s": 30.0}})
    assert seen["timeout"] == 40.0
