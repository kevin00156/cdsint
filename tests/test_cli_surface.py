# -*- coding: utf-8 -*-
"""The command line from outside: which flags parse, and what a run prints.

The COMMANDS table in cdsint/flags.py is the one description of every
command, so the tests that matter here are the ones that hold the table and
the parser against each other — a row nobody can type, or a command with no
row, is the shape the old seven-table version failed in. The rest is what a
result record says on its way out (cdsint/report.py).
"""
import json

import pytest

from cdsint import cli, flags
from cds.core.exits import EXIT_OK, EXIT_TARGET
from tests.cli_fakes import FakeRunner, compared, done

FROM_THE_FILE = "C:" + chr(92) + "p" + chr(92) + "from-the-file"


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
