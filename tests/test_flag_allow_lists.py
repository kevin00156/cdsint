# -*- coding: utf-8 -*-
"""The rows with actions say what each action takes; every other flag is
refused.

A list of what an action refuses failed open: a flag added to the row and
forgotten there was parsed by every action and read by none, the failure
cdsint/flags.py exists to prevent (kevin00156/cdsint#8).
"""
import pytest

from cdsint import flags, refusals
from cdsint.command_row import NAME

ROWS = dict((name, row) for name, row in flags.COMMANDS.items()
            if row.action is not None)


def run(argv):
    parser = flags.build_parser()
    ns = parser.parse_args(argv)
    refusals.check(parser, ns)
    return ns


def refused(argv, capsys):
    with pytest.raises(SystemExit) as stopped:
        run(argv)
    assert stopped.value.code == 2
    return capsys.readouterr().err


def test_the_rows_with_actions_are_the_ones_expected():
    assert sorted(ROWS) == ["plc", "trace"]


@pytest.mark.parametrize("name", sorted(ROWS))
def test_every_action_says_what_it_takes(name):
    row = ROWS[name]
    assert set(row.action) <= set(row.takes)


@pytest.mark.parametrize("name", sorted(ROWS))
def test_every_flag_is_taken_by_some_action(name):
    row = ROWS[name]
    taken = set(dest for dests in row.takes.values() for dest in dests)
    assert set(row.dests()) == taken


@pytest.mark.parametrize("name", sorted(ROWS))
def test_what_an_action_needs_it_takes(name):
    row = ROWS[name]
    tables = [row.needs] + list(row.form_needs.values())
    for table in tables:
        for key, dests in table.items():
            assert set(dests) <= set(row.takes[key]), (key, dests)


@pytest.fixture
def newthing(monkeypatch):
    """A flag added to both rows and to no action's list."""
    for name in ROWS:
        monkeypatch.setattr(ROWS[name], "flags", ROWS[name].flags + (
            ("--newthing", NAME, "a flag nobody listed"),))


@pytest.mark.parametrize("argv", [
    ["trace", "list", "--target", "x"],
    ["trace", "save", "--target", "x", "--name", "T1", "--out", "o"],
    ["plc", "connect", "--project", "p.project", "--install", "i",
     "--gateway", "1.2.3.4"],
])
def test_a_flag_no_action_lists_is_refused(newthing, argv, capsys):
    err = refused(argv + ["--newthing", "v"], capsys)
    assert "does not take --newthing" in err


@pytest.mark.parametrize("action,needed", [("save", ["--out", "o"]),
                                           ("show", ["--file", "t.trace"])])
def test_only_apply_takes_a_folder(action, needed, capsys):
    err = refused(["trace", action, "--target", "x", "--name", "T1",
                   "--folder", "F"] + needed, capsys)
    assert "trace %s does not take --folder" % action in err
    assert "Only trace apply takes it." in err


def test_the_sentence_names_every_action_that_takes_the_flag(capsys,
                                                             tmp_path):
    job = tmp_path / "j.json"
    job.write_text('{"task": "MainTask", "variables": ["PLC_PRG.x"]}',
                   encoding="utf-8")
    err = refused(["trace", "apply", "--target", "x", "-y", "--name", "T1",
                   "--job", str(job), "--out", "o"], capsys)
    assert "Only trace job or trace save takes it." in err
