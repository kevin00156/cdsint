# -*- coding: utf-8 -*-
"""Tests for cdsint/verify.py and the CLI surface added in phase 2.

verify is given a runner, so both forms reach it through the same code and a
fake runner is enough to pin what it asks for and what it makes of the
answers.
"""
import json

import pytest

from cdsint import cli, flags, verify
from cdsint.exits import EXIT_FAILED, EXIT_OK


class FakeRunner(object):
    """Answers run(steps) from a table, and remembers what it was asked."""

    def __init__(self, answers=None, sync=None):
        self.answers = answers or {}
        self.asked = []
        self.sync = sync

    def describe(self):
        return "a fake IDE"

    def sync_dir(self):
        return self.sync

    def run(self, steps):
        self.asked = steps
        results = []
        for command, _args in steps:
            results.append(self.answers.get(command)
                           or {"ok": True, "command": command, "data": {},
                               "elapsed_s": 1.0})
            if not results[-1]["ok"]:
                break
        return results


def failed(command, error="it broke"):
    return {"ok": False, "command": command, "error": error, "data": {},
            "elapsed_s": 1.0}


def compared(**counts):
    data = {"different": 0, "new_in_ide": 0, "new_on_disk": 0, "moved": 0}
    data.update(counts)
    return {"ok": True, "command": "compare", "data": data, "elapsed_s": 1.0}


# --- what verify asks for --------------------------------------------------

def test_the_four_steps_are_in_the_order_that_makes_them_mean_something():
    assert [name for name, _ in verify.steps()] == ["import", "export",
                                                    "compare", "build"]


def test_the_import_step_carries_the_confirmation_the_caller_already_gave():
    # -y is asked for at the CLI (below), so by the time the import step is
    # built the answer is in; the engine's own dialog must not ask again.
    assert dict(verify.steps())["import"]["yes"] is True


def test_force_reaches_the_import(monkeypatch):
    assert dict(verify.steps(force=True))["import"]["force"] is True


# --- the verdict -----------------------------------------------------------

def test_all_four_clean_is_a_pass():
    results, problems = verify.run(FakeRunner({"compare": compared()}), yes=True)
    assert len(results) == 4 and problems == []


def test_a_failed_step_is_named_and_stops_the_rest():
    runner = FakeRunner({"import": failed("import", "no sync folder")})
    results, problems = verify.run(runner, yes=True)
    assert len(results) == 1
    assert "no sync folder" in problems[0]
    assert "stopped after 1 of 4" in problems[-1]


@pytest.mark.parametrize("count", ["different", "new_in_ide", "new_on_disk",
                                   "moved"])
def test_differences_after_the_round_trip_fail_the_verify(count):
    # compare says "ok" when it finds differences, because looking is its job.
    # For verify the opposite holds: import then export then any difference
    # means the round trip lost something.
    runner = FakeRunner({"compare": compared(**{count: 2})})
    _results, problems = verify.run(runner, yes=True)
    assert problems and count in problems[0]


def test_a_build_with_errors_is_a_failure_the_build_itself_reports():
    runner = FakeRunner({"compare": compared(),
                         "build": failed("build", "12 errors")})
    _results, problems = verify.run(runner, yes=True)
    assert "12 errors" in problems[0]


# --- without -y ------------------------------------------------------------

def test_without_yes_nothing_but_compare_is_asked_for():
    # The supervisor pointed verify at an empty sync folder and its import
    # step deleted 178 of 229 objects before anything else ran. compare only
    # looks, so this is the whole of what a verify without -y may do.
    runner = FakeRunner({"compare": compared(different=3)})
    verify.run(runner)
    assert runner.asked == [("compare", {})]


def test_without_yes_the_refusal_says_what_the_import_would_have_done():
    runner = FakeRunner({"compare": compared(different=3, new_on_disk=1,
                                             new_in_ide=2)})
    results, problems = verify.run(runner)
    refusal = results[-1]
    assert refusal["command"] == "import" and refusal["ok"] is False
    assert refusal["needs_input"]["arg"] == "yes"
    assert refusal["data"] == {"modified": 3, "new_on_disk": 1, "delete": 2}
    assert problems and "-y" in problems[0]


def test_without_yes_a_clean_project_is_still_refused():
    # Nothing to import today is not permission to import tomorrow: the flag
    # says the caller means it, not that the run happens to be empty.
    _results, problems = verify.run(FakeRunner({"compare": compared()}))
    assert problems


def test_without_yes_a_compare_that_fails_is_reported_as_itself():
    runner = FakeRunner({"compare": failed("compare", "no sync folder")})
    results, problems = verify.run(runner)
    assert [r["command"] for r in results] == ["compare"]
    assert "no sync folder" in problems[0]


# --- the CLI surface -------------------------------------------------------

def parse(argv):
    return flags.build_parser().parse_args(argv)


def test_the_two_forms_cannot_be_given_together():
    # CODESYS will not open a project twice, so no run could want both.
    with pytest.raises(SystemExit):
        parse(["export", "--target", "X", "--project", "P"])


def test_a_project_only_flag_without_project_is_refused(capsys):
    # Ignoring it would drive somebody's open IDE while the caller believed
    # it was driving one of its own.
    assert cli.main(["export", "--target", "X", "--profile", "P"]) == EXIT_FAILED
    assert "only works with --project" in capsys.readouterr().err


def test_an_answer_without_an_equals_sign_is_refused(capsys):
    assert cli.main(["export", "--project", "P", "--install", "I",
                     "--sync-dir", "S", "--answer", "Upgrade"]) == EXIT_FAILED
    assert "KEY=VALUE" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [
    ["export", "--project", "P", "--install", "I"],
    ["import", "-y", "--project", "P", "--install", "I"],
    ["compare", "--project", "P", "--install", "I"],
    ["build", "--project", "P", "--install", "I"],
    ["verify", "-y", "--project", "P", "--install", "I"],
    ["config", "get", "--project", "P", "--install", "I"],
])
def test_the_project_form_has_to_say_where_the_st_files_are(argv, capsys):
    # A copy carries the original's cds-sync-folder, and that is often an
    # absolute path into the folder the original exports to — somebody's git
    # working tree. The caller of a headless run knows both paths already, so
    # it says which one it means rather than letting the copy decide.
    with pytest.raises(SystemExit) as raised:
        cli.main(argv)
    assert raised.value.code == 2
    assert "--sync-dir" in capsys.readouterr().err


def test_the_target_form_asks_the_watcher_where_its_files_are(monkeypatch):
    # There the sync folder belongs to an IDE somebody has open and set up;
    # naming it again from outside could only disagree with it.
    runner = FakeRunner()
    monkeypatch.setattr(cli, "make_runner", lambda ns: runner)
    assert cli.main(["compare", "--target", "X"]) == EXIT_OK


def test_the_project_form_says_which_folder_it_treated_as_the_truth(monkeypatch,
                                                                    capsys):
    runner = FakeRunner(sync=r"C:\tmp\sync")
    monkeypatch.setattr(cli, "make_runner", lambda ns: runner)
    cli.main(["compare", "--project", "P", "--install", "I",
              "--sync-dir", r"C:\tmp\sync"])
    assert capsys.readouterr().out.splitlines()[0] == r"sync folder: C:\tmp\sync"


def test_json_output_stays_json(monkeypatch, capsys):
    # The line above would be the first thing a caller parsing stdout reads.
    runner = FakeRunner(sync=r"C:\tmp\sync")
    monkeypatch.setattr(cli, "make_runner", lambda ns: runner)
    cli.main(["compare", "--project", "P", "--install", "I",
              "--sync-dir", r"C:\tmp\sync", "--json"])
    assert json.loads(capsys.readouterr().out)["command"] == "compare"


def test_config_get_with_no_name_asks_for_everything():
    assert flags.command_args(parse(["config", "get"])) == {"key": None,
                                                          "value": None}


def test_config_get_names_one_property():
    assert flags.command_args(parse(["config", "get", "cds-sync-debug"])) == {
        "key": "cds-sync-debug", "value": None}


def test_config_set_splits_the_assignment():
    assert flags.command_args(parse(["config", "set", "cds-sync-debug=true"])) == {
        "key": "cds-sync-debug", "value": "true"}


def test_config_set_with_an_empty_value_is_still_a_write():
    # "" and "leave it alone" are different, and only one of them is a set.
    assert flags.command_args(parse(["config", "set", "cds-sync-backup-name="])) \
        == {"key": "cds-sync-backup-name", "value": ""}


def test_verify_passes_and_says_so(monkeypatch, capsys):
    runner = FakeRunner({"compare": compared()})
    monkeypatch.setattr(cli, "make_runner", lambda ns: runner)
    assert cli.main(["verify", "-y", "--target", "X"]) == EXIT_OK
    assert "round-tripped and built cleanly" in capsys.readouterr().out


def test_verify_fails_and_says_which_step(monkeypatch, capsys):
    runner = FakeRunner({"compare": compared(different=3)})
    monkeypatch.setattr(cli, "make_runner", lambda ns: runner)
    assert cli.main(["verify", "-y", "--target", "X"]) == EXIT_FAILED
    assert "different=3" in capsys.readouterr().err


def test_verify_without_yes_exits_1_and_asks_for_it(monkeypatch, capsys):
    runner = FakeRunner({"compare": compared(new_in_ide=229)})
    monkeypatch.setattr(cli, "make_runner", lambda ns: runner)
    assert cli.main(["verify", "--target", "X"]) == EXIT_FAILED
    assert runner.asked == [("compare", {})]
    assert "-y" in capsys.readouterr().err


def test_verify_with_yes_runs_the_round_trip(monkeypatch):
    runner = FakeRunner({"compare": compared()})
    monkeypatch.setattr(cli, "make_runner", lambda ns: runner)
    assert cli.main(["verify", "-y", "--target", "X"]) == EXIT_OK
    assert [name for name, _ in runner.asked] == ["import", "export",
                                                  "compare", "build"]
