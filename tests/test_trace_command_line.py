# -*- coding: utf-8 -*-
"""What `cdsint trace` looks like from outside the IDE.

Four actions on one row. job and apply have both forms; save and show only
the watcher's, because recorded data lives in the IDE that recorded it, and
the refusal says so rather than "unrecognized". Files are flags, as plc
trace's --job is, and every path arrives at the IDE side absolute: its
working directory is not the shell's.
"""
import os

import pytest

from cdsint import flags, refusals


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


def write_job(tmp_path, text):
    path = tmp_path / "j.json"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_trace_job_goes_out_under_its_wire_name_with_an_absolute_out():
    ns = parse(["trace", "job", "--target", "x", "--name", "T1",
                "--out", "j.json"])
    assert flags.wire_name(ns) == "trace job"
    assert flags.command_args(ns)["out"] == os.path.abspath("j.json")


def test_trace_job_has_a_project_form():
    ns = parse(["trace", "job", "--project", "p.project", "--install", "i",
                "--name", "T1"])
    assert flags.wire_name(ns) == "trace job"


@pytest.mark.parametrize("action,rest", [
    ("save", ["--name", "T1", "--out", "o"]),
    ("show", ["--file", "a.trace"]),
])
def test_data_actions_have_no_project_form(action, rest, capsys):
    err = refused(["trace", action, "--project", "p", "--install", "i"]
                  + rest, capsys)
    assert "Recorded data lives only in the IDE" in err


def test_apply_takes_a_definition_without_run_keys(tmp_path):
    job = write_job(tmp_path,
                    '{"task": "MainTask", "variables": ["PLC_PRG.n"]}')
    ns = parse(["trace", "apply", "--target", "x", "-y", "--name", "T1",
                "--job", job])
    assert flags.command_args(ns)["job"] == {
        "task": "MainTask", "variables": ["PLC_PRG.n"], "resolution": "us",
        "every_n_cycles": 1}


def test_apply_refuses_a_job_that_is_wrong(tmp_path, capsys):
    job = write_job(tmp_path, '{"task": "MainTask"}')
    err = refused(["trace", "apply", "--target", "x", "--name", "T1",
                   "--job", job], capsys)
    assert "variables is required" in err


def test_show_needs_a_name_and_takes_a_confirmation(tmp_path, capsys):
    shown = str(tmp_path / "t.trace")
    err = refused(["trace", "show", "--target", "x", "--file", shown, "-y"],
                  capsys)
    assert "trace show needs --name" in err
    ns = parse(["trace", "show", "--target", "x", "--file", shown,
                "--name", "T1", "-y"])
    assert ns.name == "T1" and ns.yes is True


def test_only_the_actions_that_change_a_trace_take_yes(capsys):
    err = refused(["trace", "job", "--target", "x", "--name", "T1", "-y"],
                  capsys)
    assert "trace job does not take --yes" in err


@pytest.mark.parametrize("argv,missing", [
    (["trace", "job", "--target", "x"], "--name"),
    (["trace", "save", "--target", "x", "--name", "T1"], "--out"),
    (["trace", "show", "--target", "x"], "--file"),
])
def test_what_each_action_cannot_run_without(argv, missing, capsys):
    assert "needs %s" % missing in refused(argv, capsys)


def test_formats_are_words_the_ide_can_save():
    ns = parse(["trace", "save", "--target", "x", "--name", "T1",
                "--out", "o", "--formats", "csv,txt"])
    assert flags.command_args(ns)["formats"] == ["csv", "txt"]


def test_a_format_the_ide_cannot_save_is_refused(capsys):
    err = refused(["trace", "save", "--target", "x", "--name", "T1",
                   "--out", "o", "--formats", "csv,xlsx"], capsys)
    assert "xlsx" in err
