# -*- coding: utf-8 -*-
"""What `cdsint trace` looks like from outside the IDE.

Five actions on one row. list, job and apply have both forms; save and show
only the watcher's, because recorded data lives in the IDE that recorded it,
and the refusal says so rather than "unrecognized". Files are flags, as plc
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


def test_a_list_of_variable_names_prints_one_name_a_line(capsys):
    # trace apply and trace show carry `variables` as names, not as the
    # rows a recording judged; the bench found the printer taking the one
    # for the other and stopping the CLI with a traceback.
    from cds.core import commands
    from cdsint import report
    record = commands.new_result(commands.new_command("trace apply"), True,
                                 data={"variables": ["PLC_PRG.a",
                                                     "PLC_PRG.b"]})
    report.show(record)
    shown = capsys.readouterr().out
    assert "PLC_PRG.a" in shown and "PLC_PRG.b" in shown



def test_trace_list_takes_both_forms_and_no_flags(capsys):
    assert flags.wire_name(parse(["trace", "list", "--target", "x"])) \
        == "trace list"
    parse(["trace", "list", "--project", "p.project", "--install", "i"])
    err = refused(["trace", "list", "--target", "x", "--name", "T1"], capsys)
    assert "trace list does not take --name" in err


def test_only_apply_takes_a_folder(tmp_path, capsys):
    job = write_job(tmp_path, '{"task": "T", "variables": ["a"]}')
    ns = parse(["trace", "apply", "--target", "x", "-y", "--name", "T1",
                "--job", job, "--folder", "Traces"])
    assert ns.folder == "Traces"
    err = refused(["trace", "job", "--target", "x", "--name", "T1",
                   "--folder", "F"], capsys)
    assert "trace job does not take --folder" in err


def test_trace_list_prints_a_line_per_trace(capsys):
    from cds.core import commands
    from cdsint import report
    record = commands.new_result(commands.new_command("trace list"), True,
                                 data={"traces": [
                                     {"name": "T1", "path": "App/Traces/T1",
                                      "task": "MainTask",
                                      "variables": ["a", "b"],
                                      "left_out": ["c"], "unread": None},
                                     {"name": "T2", "path": "App/T2",
                                      "task": None, "variables": [],
                                      "left_out": [], "unread": "no member"}]})
    report.show(record)
    shown = capsys.readouterr().out
    assert "App/Traces/T1  MainTask  2 variable(s), 1 switched off" in shown
    assert "App/T2  (not read: no member)" in shown


def test_trace_list_marks_a_trace_it_could_not_read_even_without_a_reason(
        capsys):
    from cds.core import commands
    from cdsint import report
    record = commands.new_result(commands.new_command("trace list"), True,
                                 data={"traces": [
                                     {"name": "T2", "path": "App/T2",
                                      "task": None, "variables": [],
                                      "left_out": [], "unread": ""}]})
    report.show(record)
    assert "App/T2  (not read" in capsys.readouterr().out


def test_a_list_another_command_names_like_a_trace_list_prints_plainly(
        capsys):
    """Row printers belong to the command whose rows they were written for
    (#9): a plc command reporting trace names is not trace list."""
    from cds.core import commands
    from cdsint import report
    record = commands.new_result(commands.new_command("plc connect"), True,
                                 data={"traces": ["T1", "T2"],
                                       "variables": ["a.x"]})
    report.show(record)
    shown = capsys.readouterr().out
    assert "T1" in shown and "T2" in shown and "a.x" in shown


def test_trace_save_prints_how_much_of_each_variable_came_back(capsys):
    from cds.core import commands
    from cdsint import report
    record = commands.new_result(commands.new_command("trace save"), True,
                                 data={"variables": [
                                     {"name": "a.x", "samples": 9,
                                      "expected": 10, "complete": 0.9,
                                      "gaps": [{}],
                                      "longest_interval": 2}]})
    report.show(record)
    assert "a.x  9/10 samples  complete 0.9  gaps 1" in \
        capsys.readouterr().out
