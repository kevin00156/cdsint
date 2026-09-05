# -*- coding: utf-8 -*-
"""Tests for cdsint/verify.py and the CLI surface added in phase 2.

verify is given a runner, so both forms reach it through the same code and a
fake runner is enough to pin what it asks for and what it makes of the
answers.
"""
import pytest

from cdsint import cli, verify
from cdsint.exits import EXIT_FAILED, EXIT_OK


class FakeRunner(object):
    """Answers run(steps) from a table, and remembers what it was asked."""

    def __init__(self, answers=None):
        self.answers = answers or {}
        self.asked = []

    def describe(self):
        return "a fake IDE"

    def sync_dir(self):
        return None

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


def test_the_import_is_confirmed_because_importing_is_what_verify_means():
    # SPEC 4.2 lists verify without a -y of its own, so asking would be a
    # question with only one useful answer.
    assert dict(verify.steps())["import"]["yes"] is True


def test_force_reaches_the_import(monkeypatch):
    assert dict(verify.steps(force=True))["import"]["force"] is True


# --- the verdict -----------------------------------------------------------

def test_all_four_clean_is_a_pass():
    results, problems = verify.run(FakeRunner({"compare": compared()}))
    assert len(results) == 4 and problems == []


def test_a_failed_step_is_named_and_stops_the_rest():
    runner = FakeRunner({"import": failed("import", "no sync folder")})
    results, problems = verify.run(runner)
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
    _results, problems = verify.run(runner)
    assert problems and count in problems[0]


def test_a_build_with_errors_is_a_failure_the_build_itself_reports():
    runner = FakeRunner({"compare": compared(),
                         "build": failed("build", "12 errors")})
    _results, problems = verify.run(runner)
    assert "12 errors" in problems[0]


# --- the CLI surface -------------------------------------------------------

def parse(argv):
    return cli.build_parser().parse_args(argv)


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
                     "--answer", "Upgrade"]) == EXIT_FAILED
    assert "KEY=VALUE" in capsys.readouterr().err


def test_config_get_with_no_name_asks_for_everything():
    assert cli.command_args(parse(["config", "get"])) == {"key": None,
                                                          "value": None}


def test_config_get_names_one_property():
    assert cli.command_args(parse(["config", "get", "cds-sync-debug"])) == {
        "key": "cds-sync-debug", "value": None}


def test_config_set_splits_the_assignment():
    assert cli.command_args(parse(["config", "set", "cds-sync-debug=true"])) == {
        "key": "cds-sync-debug", "value": "true"}


def test_config_set_with_an_empty_value_is_still_a_write():
    # "" and "leave it alone" are different, and only one of them is a set.
    assert cli.command_args(parse(["config", "set", "cds-sync-backup-name="])) \
        == {"key": "cds-sync-backup-name", "value": ""}


def test_verify_passes_and_says_so(monkeypatch, capsys):
    runner = FakeRunner({"compare": compared()})
    monkeypatch.setattr(cli, "make_runner", lambda ns: runner)
    assert cli.main(["verify", "--target", "X"]) == EXIT_OK
    assert "round-tripped and built cleanly" in capsys.readouterr().out


def test_verify_fails_and_says_which_step(monkeypatch, capsys):
    runner = FakeRunner({"compare": compared(different=3)})
    monkeypatch.setattr(cli, "make_runner", lambda ns: runner)
    assert cli.main(["verify", "--target", "X"]) == EXIT_FAILED
    assert "different=3" in capsys.readouterr().err
