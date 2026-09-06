# -*- coding: utf-8 -*-
"""Tests for cdsint/verify.py and the CLI surface added in phase 2.

verify is given a runner, so both forms reach it through the same code and a
fake runner is enough to pin what it asks for and what it makes of the
answers.
"""
import json

import pytest

from cdsint import cli, flags, verify
from cds.core import commands
from cds.core.exits import (EXIT_DENIED, EXIT_FAILED, EXIT_OK,
                            EXIT_TARGET)


FROM_THE_FILE = "C:" + chr(92) + "p" + chr(92) + "from-the-file"


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
            results.append(self.answers.get(command) or done(command))
            if not results[-1]["ok"]:
                break
        return results


def record(command, ok, **rest):
    """One result, built the way every real producer builds one.

    Not a dict literal with the four fields a test happens to read: the
    printer indexes all twelve now, because a record that is short of one is
    a producer that forgot it (cds/core/commands.py new_result).
    """
    return commands.new_result(commands.new_command(command), ok, **rest)


def done(command, **rest):
    rest.setdefault("data", {})
    return record(command, True, **rest)


def failed(command, error="it broke"):
    return record(command, False, error=error, data={})


def compared(**counts):
    data = {"different": 0, "new_in_ide": 0, "new_on_disk": 0, "moved": 0}
    data.update(counts)
    return done("compare", data=data)


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


# --- the CLI surface -------------------------------------------------------

def parse(argv):
    return flags.build_parser().parse_args(argv)


def test_the_two_forms_cannot_be_given_together():
    # CODESYS will not open a project twice, so no run could want both.
    with pytest.raises(SystemExit):
        parse(["export", "--target", "X", "--project", "P"])


def test_a_project_only_flag_without_project_is_refused(capsys):
    # Ignoring it would drive somebody's open IDE while the caller believed
    # it was driving one of its own. Exit 2, like every other "these flags do
    # not go together" (SPEC 4.3): nothing ran, so 1 would be a lie.
    with pytest.raises(SystemExit) as raised:
        cli.main(["export", "--target", "X", "--profile", "P"])
    assert raised.value.code == EXIT_TARGET
    assert "only works with --project" in capsys.readouterr().err


def test_an_answer_without_an_equals_sign_is_refused(capsys):
    # Exit 2, not 1: nothing ran. It used to be parsed after argparse had
    # finished, so a malformed one came back as "the command failed".
    with pytest.raises(SystemExit) as raised:
        cli.main(["export", "--project", "P", "--install", "I",
                  "--sync-dir", "S", "--answer", "Upgrade"])
    assert raised.value.code == EXIT_TARGET
    assert "KEY=VALUE" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [
    ["export", "--project", "P", "--install", "I"],
    ["import", "-y", "--project", "P", "--install", "I"],
    ["compare", "--project", "P", "--install", "I"],
    ["build", "--project", "P", "--install", "I"],
    ["verify", "-y", "--project", "P", "--install", "I"],
])
def test_the_project_form_no_longer_has_to_say_where_the_st_files_are(argv):
    # It was compulsory while a copy of a .project carried the original's
    # sync folder inside it, which on this machine is an absolute path into
    # somebody's git working tree. The settings live beside the project now
    # (SPEC D10), so a copy of the .project alone carries nothing and the
    # parser has nothing to protect the caller from.
    assert flags.build_parser().parse_args(argv).sync_dir is None


def test_a_deleted_flag_is_refused_by_name(capsys):
    # --force went with the version and computer stamps (SPEC 6.7). With
    # argparse abbreviations on it would have been read as --force-lock, and
    # a stale script would quietly start opening projects another IDE holds.
    with pytest.raises(SystemExit) as raised:
        cli.main(["import", "-y", "--force", "--target", "X"])
    assert raised.value.code == 2
    assert "unrecognized arguments: --force" in capsys.readouterr().err


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



def test_the_folder_it_names_is_the_one_the_run_reported(monkeypatch, capsys):
    # Without --sync-dir nobody out here knows the answer until the IDE has
    # read the project's settings file, so the line comes from the result
    # rather than from the flag (SPEC 4.2).
    answered = {"compare": dict(done("compare"), sync_dir=FROM_THE_FILE)}
    runner = FakeRunner(answered)
    monkeypatch.setattr(cli, "make_runner", lambda ns: runner)
    cli.main(["compare", "--project", "P", "--install", "I"])
    assert capsys.readouterr().out.splitlines()[0] ==         "sync folder: " + FROM_THE_FILE



def test_json_output_stays_json(monkeypatch, capsys):
    # The line above would be the first thing a caller parsing stdout reads.
    runner = FakeRunner(sync=r"C:\tmp\sync")
    monkeypatch.setattr(cli, "make_runner", lambda ns: runner)
    cli.main(["compare", "--project", "P", "--install", "I",
              "--sync-dir", r"C:\tmp\sync", "--json"])
    assert json.loads(capsys.readouterr().out)["command"] == "compare"


def test_a_json_run_gets_the_notes_in_the_record_not_on_stderr(monkeypatch,
                                                               capsys):
    # A lock we cleared, an IDE we had to kill, an exit code we cannot vouch
    # for: prose on stderr is invisible to a caller parsing stdout, and it
    # had no way to attach it to anything even if it read both.
    noted = dict(done("compare"), notes=["removed a lock file we left"])
    runner = FakeRunner({"compare": noted})
    monkeypatch.setattr(cli, "make_runner", lambda ns: runner)

    cli.main(["compare", "--project", "P", "--install", "I", "--json"])

    printed = capsys.readouterr()
    assert json.loads(printed.out)["notes"] == ["removed a lock file we left"]
    assert printed.err == ""


def test_the_same_run_without_json_says_it_out_loud(monkeypatch, capsys):
    noted = dict(done("compare"), notes=["removed a lock file we left"])
    runner = FakeRunner({"compare": noted})
    monkeypatch.setattr(cli, "make_runner", lambda ns: runner)

    cli.main(["compare", "--project", "P", "--install", "I"])

    assert "removed a lock file" in capsys.readouterr().err


def test_a_note_is_said_once_however_many_steps_carried_it(monkeypatch,
                                                           capsys):
    # The launcher hangs the same list on every record it hands back, so a
    # reader of any one of them hears about the lock. A person reading all
    # four should not hear it four times.
    note = "removed a lock file we left"
    answers = dict((name, dict(done(name), notes=[note]))
                   for name in ("import", "export", "compare", "build"))
    answers["compare"] = dict(compared(), notes=[note])
    runner = FakeRunner(answers)
    monkeypatch.setattr(cli, "make_runner", lambda ns: runner)

    assert cli.main(["verify", "-y", "--project", "P", "--install",
                     "I"]) == EXIT_OK

    assert capsys.readouterr().err.count(note) == 1


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


# --- the table is the command line -----------------------------------------

def test_every_row_in_the_table_is_a_command_you_can_type(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    printed = capsys.readouterr().out
    for name in flags.COMMANDS:
        assert name in printed, name + " is in the table but not in --help"


def test_every_command_you_can_type_is_a_row_in_the_table():
    parser = flags.build_parser()
    choices = [action.choices for action in parser._subparsers._actions
               if action.choices]
    assert set(choices[0]) == set(flags.COMMANDS)


def test_a_flag_keeps_its_own_default_after_the_gaps_are_filled():
    # set_defaults overwrites a matching action's default rather than filling
    # a gap, so telling every subparser about every attribute used to replace
    # --answer's empty list with None. Nothing broke, because cli._answers
    # took None; the next repeatable flag would not be so lucky.
    parser = flags.build_parser()
    assert parser.parse_args(["export"]).answer == []
    # And a subcommand that does not have the flag still answers to the name.
    assert parser.parse_args(["list"]).answer is None


def test_the_row_and_the_parser_agree_about_what_a_command_carries():
    # Command.carries() is worked out from the row, and it decides which
    # defaults are safe to set. If it ever named one the parser also defines,
    # that flag's declared default would be silently replaced -- which is the
    # bug above, in a form no test would see.
    parser = flags.build_parser()
    subcommands = [action.choices for action in parser._subparsers._actions
                   if action.choices][0]
    for name, command in subcommands.items():
        added = set(action.dest for action in command._actions
                    if action.dest not in ("help", "timeout", "json"))
        assert added == flags.COMMANDS[name].carries(), name


def test_every_command_line_is_the_same_shape():
    # cdsint/cli.py reads ns.project whichever subcommand ran. A namespace
    # missing an attribute would send it back to getattr with a default, and
    # that reads the same whether the flag was left out or never existed.
    parser = flags.build_parser()
    for argv in (["installs"], ["list"], ["ping"], ["export"],
                 ["plc", "connect", "--project", "P"]):
        given = vars(parser.parse_args(argv))
        missing = [name for name in flags.EVERY_ATTRIBUTE
                   if name not in given]
        assert not missing, "%s has no %s" % (argv, missing)
