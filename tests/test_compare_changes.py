# -*- coding: utf-8 -*-
"""compare's per-object answer, and the printer that no longer names it.

compare's counts say how many objects differ; the list of which ones was only
ever on stdout, so cdsint/report.py had a branch that showed the tail when
the command happened to be called "compare". The list is in `data` now, the
same shape discover uses for the type GUIDs it did not recognise, and the
printer shows it the way it shows any other list (SPEC 4.3).
"""
import pytest

from cds.core import commands
from cdsint import report


@pytest.fixture
def compare(load_engine):
    for dep in ("codesys_constants", "codesys_utils", "codesys_managers",
                "codesys_compare_engine"):
        load_engine(dep)
    return load_engine("entry_compare")


def ide_object(name, path):
    return {"name": name, "path": path, "type": "pou"}


def test_a_changed_object_is_one_row(compare):
    rows = compare.changed_objects([ide_object("Main", "POUs/Main.st")],
                                   [], [], [])
    assert rows == [{"name": "Main", "path": "POUs/Main.st",
                     "state": "changed"}]


def test_each_kind_of_difference_says_which_it_is(compare):
    rows = compare.changed_objects(
        [ide_object("Main", "POUs/Main.st")],
        [ide_object("OnlyHere", "POUs/OnlyHere.st")],
        [{"name": "Newcomer", "path": "POUs/Newcomer.st"}],
        [{"name": "Moved", "ide_path": "A/Moved.st",
          "disk_path": "B/Moved.st"}])
    assert [row["state"] for row in rows] == ["changed", "new_in_ide",
                                              "new_on_disk", "moved"]


def test_a_move_carries_both_ends(compare):
    # Which is the whole of what a move is; the others are in one place.
    rows = compare.changed_objects([], [], [], [
        {"name": "Moved", "ide_path": "A/Moved.st",
         "disk_path": "B/Moved.st"}])
    assert rows[0]["path"] == "A/Moved.st -> B/Moved.st"


def test_no_differences_is_an_empty_list_not_a_missing_field(compare):
    assert compare.changed_objects([], [], [], []) == []


def test_every_row_is_the_three_fields_the_printer_lays_out(compare):
    rows = compare.changed_objects([ide_object("Main", "POUs/Main.st")],
                                   [], [], [])
    assert sorted(rows[0]) == ["name", "path", "state"]


# --- and the printer -------------------------------------------------------

def result(ok, **rest):
    return commands.new_result(commands.new_command("compare"), ok, **rest)


def test_the_summary_prints_the_rows(capsys):
    report.show(result(True, data={"changes": [
        {"name": "Main", "path": "POUs/Main.st", "state": "changed"}]}))
    printed = capsys.readouterr().out
    assert "POUs/Main.st" in printed and "changed" in printed


def test_a_run_that_worked_does_not_get_the_tail(capsys):
    report.show(result(True, data={"changes": []},
                       stdout_tail="200 lines of progress"))
    assert "200 lines" not in capsys.readouterr().err


def test_a_run_that_failed_still_gets_the_tail(capsys):
    report.show(result(False, error="it broke",
                       stdout_tail="the traceback that says why"))
    assert "says why" in capsys.readouterr().err
