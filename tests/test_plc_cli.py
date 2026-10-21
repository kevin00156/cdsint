# -*- coding: utf-8 -*-
"""What the two plc commands look like from outside the IDE.

Which form they take (--project only, SPEC D8), which exit code each
outcome earns (SPEC 4.3), and that a refusal survives the trip out
through a result record rather than arriving as a plain failure.
"""
import os

import pytest

from cds.core import commands
from cds.core.exits import EXIT_DENIED, EXIT_FAILED, EXIT_OK
from cds.ide import entries, permit
from cdsint import cli, flags, refusals
from tests.plc_fakes import ide
from tests.plc_fakes import (   # noqa: F401  autouse fixtures
    fake_codesys_ui, keep_the_engine_loaded, workspace)


def record(ok, **rest):
    """One result record, built the way every producer builds one."""
    return commands.new_result(commands.new_command("plc download"), ok,
                               **rest)


def test_a_refusal_is_exit_5_and_a_failure_is_exit_1():
    denied = record(False, error="not allowed",
                    denied=permit.record(None, "download"))
    assert cli.exit_code(denied) == EXIT_DENIED
    assert cli.exit_code(record(False, error="it broke")) == EXIT_FAILED
    assert cli.exit_code(record(True)) == EXIT_OK


class FakeRunner(object):
    """Answers run(steps) with one record, and remembers what it was asked."""

    def __init__(self, record):
        self.record = record
        self.asked = []

    def describe(self):
        return "a fake IDE"

    def sync_dir(self):
        return os.path.join("C:" + os.sep, "tmp", "sync")

    def run(self, steps):
        self.asked = steps
        return [dict(self.record, command=steps[0][0])]


def drive(monkeypatch, record):
    runner = FakeRunner(record)
    monkeypatch.setattr(cli, "make_runner", lambda ns: runner)
    return runner


def test_a_project_that_forbids_it_comes_back_as_exit_5(monkeypatch, capsys):
    projects = ide(allowed=None)["projects"]
    said = permit.refusal(projects, "download")
    drive(monkeypatch, record(False, error=said,
                              denied=permit.record(projects, "download")))
    code = cli.main(["plc", "download", "-y", "--project", "P", "--install",
                     "I", "--sync-dir", "S", "--gateway", "192.168.1.5"])
    assert code == EXIT_DENIED
    assert "plc" in capsys.readouterr().err


def test_a_download_with_no_yes_comes_back_as_exit_1(monkeypatch, capsys):
    # Not 5: the settings file allows it and a flag would fix this, which is a
    # different next move for whoever is reading the code.
    question = "Confirm PLC Download: ..."
    drive(monkeypatch, record(False, error=question,
                              needs_input={"question": question,
                                           "arg": "yes"}))
    code = cli.main(["plc", "download", "--project", "P", "--install", "I",
                     "--sync-dir", "S", "--gateway", "192.168.1.5"])
    assert code == EXIT_FAILED
    assert "--yes" in capsys.readouterr().err


def test_a_match_comes_back_as_exit_0(monkeypatch):
    runner = drive(monkeypatch, record(True, data={"crc": "MATCH"}))
    assert cli.main(["plc", "connect", "--project", "P", "--install", "I",
                     "--sync-dir", "S", "--gateway", "192.168.1.5"]) == EXIT_OK
    assert runner.asked[0][0] == "plc connect"


def test_the_refusal_survives_the_trip_through_a_result_record():
    # exit 5 is decided from the record the CLI reads back, so the field has
    # to be in it — both forms write results through this one function.
    record = commands.new_result({"id": "1", "command": "plc download"},
                                 False, error="nope",
                                 denied=permit.record(None, "download"))
    assert cli.exit_code(record) == EXIT_DENIED


# --------------------------------------------------------------------------

# Only the --project form (SPEC D8)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("argv", [
    ["plc", "connect", "--target", "X"],
    ["plc", "download", "-y", "--target", "X"],
])
def test_the_watcher_form_is_refused_with_the_reason(argv, capsys):
    with pytest.raises(SystemExit) as raised:
        cli.main(argv)
    assert raised.value.code == 2
    said = capsys.readouterr().err
    assert "online session" in said and "D8" in said


def test_neither_form_named_is_refused_the_same_way(capsys):
    with pytest.raises(SystemExit) as raised:
        cli.main(["plc", "connect"])
    assert raised.value.code == 2
    assert "--project" in capsys.readouterr().err


def test_the_project_form_no_longer_has_to_say_where_the_st_files_are():
    # --sync-dir was compulsory while a copy of a .project carried the
    # original's sync folder inside it. The settings live beside the project
    # now, so a copy of the .project alone carries nothing (SPEC 4.2), and
    # the parser lets the command through to look for a settings file.
    parsed = flags.build_parser().parse_args(
        ["plc", "connect", "--project", "P", "--install", "I"])
    assert parsed.sync_dir is None


def test_the_watcher_will_not_log_in_to_a_plc():
    # plc trace runs there through the person's own login (SPEC 6.8).
    assert "plc connect" not in entries.COMMANDS
    assert "plc download" not in entries.COMMANDS
    assert set(entries.WATCHER_REFUSES) == {"plc connect", "plc download"}


def test_the_watcher_refuses_by_name_rather_than_pretending_not_to_know():
    # A hand-written command file is the way one gets there, and "unknown
    # command" would send the reader looking for a typo.
    for reason in entries.WATCHER_REFUSES.values():
        assert "--project" in reason and "D8" in reason


def test_each_action_reaches_its_own_function():
    assert entries.SCRIPTS["plc connect"] == ("entry_plc.py", "connect")
    assert entries.SCRIPTS["plc download"] == ("entry_plc.py", "download")
    assert entries.SCRIPTS["plc trace"] == ("entry_plc.py", "record")


def test_the_cli_spells_the_action_into_the_command_name():
    parsed = flags.build_parser().parse_args(
        ["plc", "download", "-y", "--project", "P", "--install", "I",
         "--sync-dir", "S"])
    assert flags.wire_name(parsed) == "plc download"
    assert flags.command_args(parsed) == {"yes": True, "gateway": None,
                                        "port": None, "gateway_name": None,
                                        "job": None, "name": None,
                                        "stop": None, "method": None,
                                        "no_boot_app": None}


def test_the_gateway_flags_reach_the_body():
    parsed = flags.build_parser().parse_args(
        ["plc", "connect", "--project", "P", "--install", "I", "--sync-dir",
         "S", "--gateway", "192.168.1.5", "--port", "11740",
         "--gateway-name", "Gateway-3"])
    assert flags.command_args(parsed) == {"yes": None, "gateway": "192.168.1.5",
                                        "port": 11740,
                                        "gateway_name": "Gateway-3",
                                        "job": None, "name": None,
                                        "stop": None, "method": None,
                                        "no_boot_app": None}


# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# plc login, logout, run and stop: the watcher's own application
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def a_login_in_the_environment(monkeypatch):
    """The flags are what these pin; a watcher online command without the
    device login is refused as well (tests/test_plc_credentials.py)."""
    monkeypatch.setenv("CDS_DEV_USER", "dev")
    monkeypatch.setenv("CDS_DEV_PASS", "pw")


def parse(argv):
    parser = flags.build_parser()
    ns = parser.parse_args(argv)
    refusals.check(parser, ns)
    return ns


def refused(argv, capsys):
    with pytest.raises(SystemExit) as raised:
        parse(argv)
    assert raised.value.code == 2
    return capsys.readouterr().err


def test_a_bare_login_says_nothing_it_did_not_say():
    ns = parse(["plc", "login", "--target", "X"])
    assert flags.wire_name(ns) == "plc login"
    args = flags.command_args(ns)
    assert args["method"] is None and args["no_boot_app"] is None
    assert args["yes"] is None


def test_login_takes_a_method_a_yes_and_no_boot_app():
    ns = parse(["plc", "login", "--target", "X", "--method", "online_change",
                "-y", "--no-boot-app"])
    args = flags.command_args(ns)
    assert (args["method"], args["yes"], args["no_boot_app"]) == (
        "online_change", True, True)


@pytest.mark.parametrize("method", ["online-change", "full"])
def test_a_method_outside_the_two_is_refused(method, capsys):
    refused(["plc", "login", "--target", "X", "--method", method], capsys)


@pytest.mark.parametrize("action", ["login", "logout", "run", "stop"])
def test_the_four_have_only_the_target_form(action, capsys):
    err = refused(["plc", action, "--project", "P", "--install", "I"], capsys)
    assert "--target" in err and "no --project form" in err


def test_login_cannot_aim_the_controller(capsys):
    err = refused(["plc", "login", "--target", "X", "--gateway", "1.2.3.4"],
                  capsys)
    assert "does not take --gateway" in err and "device" in err


@pytest.mark.parametrize("argv", [
    ["plc", "logout", "--target", "X", "--method", "download"],
    ["plc", "run", "--target", "X", "--method", "download"],
    ["plc", "stop", "--target", "X", "--no-boot-app"],
    ["plc", "logout", "--target", "X", "-y"],
])
def test_the_rest_refuse_what_they_never_read(argv, capsys):
    refused(argv, capsys)


@pytest.mark.parametrize("action", ["run", "stop"])
def test_run_and_stop_take_a_yes(action):
    assert parse(["plc", action, "--target", "X", "-y"]).yes is True


def test_trace_takes_no_yes_and_the_sentence_names_who_does(tmp_path, capsys):
    job = tmp_path / "j.json"
    job.write_text('{"duration_s": 1, "out": "o"}', encoding="utf-8")
    err = refused(["plc", "trace", "--target", "X", "--name", "T", "--job",
                   str(job), "-y"], capsys)
    assert "plc download" in err and "plc login" in err
    assert "plc run" in err and "plc stop" in err


def test_the_watcher_points_a_download_at_login(capsys):
    err = refused(["plc", "download", "--target", "X", "-y"], capsys)
    assert "plc login --method download" in err


def test_the_four_reach_distinct_functions():
    # Not run/stop: entry_plc.py is exec'd into the IDE's namespace.
    assert entries.SCRIPTS["plc login"] == ("entry_plc.py", "log_in")
    assert entries.SCRIPTS["plc logout"] == ("entry_plc.py", "log_out")
    assert entries.SCRIPTS["plc run"] == ("entry_plc.py", "run_application")
    assert entries.SCRIPTS["plc stop"] == ("entry_plc.py", "stop_application")


def test_the_headless_launcher_refuses_the_four_by_name():
    for name in ("plc login", "plc logout", "plc run", "plc stop"):
        assert "--target" in entries.HEADLESS_REFUSES[name]
