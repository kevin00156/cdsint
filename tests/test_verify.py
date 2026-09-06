# -*- coding: utf-8 -*-
"""Tests for cdsint/verify.py: the four steps, and what they add up to.

verify is given a runner, so both forms reach it through the same code and
a fake runner is enough to pin what it asks for and what it makes of the
answers. The command line it is reached through is test_cli_surface.py.
"""
import pytest

from cdsint import cli, verify
from cds.core.exits import EXIT_DENIED, EXIT_FAILED, EXIT_OK
from tests.cli_fakes import FakeRunner, compared, failed, record

FROM_THE_FILE = "C:" + chr(92) + "p" + chr(92) + "from-the-file"


# --- what verify asks for --------------------------------------------------

def test_the_four_steps_are_in_the_order_that_makes_them_mean_something():
    assert [name for name, _ in verify.steps()] == ["import", "export",
                                                    "compare", "build"]


def test_the_import_step_carries_the_confirmation_the_caller_already_gave():
    # -y is asked for at the CLI (below), so by the time the import step is
    # built the answer is in; the engine's own dialog must not ask again.
    assert dict(verify.steps())["import"]["yes"] is True


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


def test_there_is_no_config_command(capsys):
    # The file is the interface (SPEC 4.2). A command that edited it would be
    # a second editor for the same eleven keys, and the validation would have
    # to exist twice.
    with pytest.raises(SystemExit) as raised:
        cli.main(["config", "get"])
    assert raised.value.code == 2
    assert "invalid choice: 'config'" in capsys.readouterr().err


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


def test_a_step_the_project_refuses_is_exit_5(monkeypatch, capsys):
    # verify used to decide its own exit code, so a step stopped by the
    # project's `plc` list came back as 1 -- which tells the reader to fix a
    # flag when the fix is a word in a file (SPEC 4.3, 6.5).
    refused = record("import", False, error="this project does not allow it",
                     denied={"file": "Line.cdsint.json", "key": "plc",
                             "action": "download"})
    runner = FakeRunner({"import": refused})
    monkeypatch.setattr(cli, "make_runner", lambda ns: runner)
    assert cli.main(["verify", "-y", "--target", "X"]) == EXIT_DENIED
    assert "import failed" in capsys.readouterr().err


def test_the_refusal_without_yes_is_a_whole_result_record():
    # It reaches cdsint/report.py through the same door as every real answer,
    # and that printer indexes all twelve fields now.
    refusal = verify.needs_yes({"different": 2})
    assert sorted(refusal) == sorted(record("import", False,
                                            error="x"))
    assert refusal["denied"] is None
    assert refusal["needs_input"]["arg"] == "yes"
    assert refusal["data"]["modified"] == 2
