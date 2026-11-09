# -*- coding: utf-8 -*-
"""A file left mid-merge by git is refused, not imported as code.

After a `git pull` with an unresolved conflict in PLC_PRG.st, import wrote
the <<<<<<< lines into the POU, and the build errors pointed at the markers
instead of at the merge nobody had finished.
"""
import pytest

from cds.core.conflict_markers import has_conflict
from tests.sync_bench import Bench, folder, pou

CONFLICT = (u"<<<<<<< HEAD\n"
            u"x := 2;\n"
            u"=======\n"
            u"x := 3;\n"
            u">>>>>>> origin/main\n")


def test_a_git_conflict_is_found():
    assert has_conflict(u"PROGRAM P\n" + CONFLICT)


def test_crlf_line_ends_do_not_hide_it():
    assert has_conflict(CONFLICT.replace(u"\n", u"\r\n"))


def test_markers_inside_a_line_are_not_a_conflict():
    text = (u"s := '<<<<<<< HEAD'; // >>>>>>> not a marker\n"
            u"(* see <<<<<<< and >>>>>>> in the git manual *)\n")
    assert not has_conflict(text)


def test_a_divider_of_equals_signs_is_not_a_conflict():
    assert not has_conflict(u"(*\n=======\nNotes\n=======\n*)\n")


def test_one_end_alone_is_not_a_conflict():
    assert not has_conflict(u"<<<<<<< HEAD\nx := 1;\n")
    assert not has_conflict(u">>>>>>> HEAD\n<<<<<<< HEAD\n")


def test_a_longer_run_of_brackets_is_not_a_marker():
    assert not has_conflict(u"<<<<<<<<\nx\n>>>>>>>>\n")


@pytest.fixture
def bench(monkeypatch, tmp_path):
    made = Bench(monkeypatch, tmp_path, folder("A", pou("Foo"), pou("Bar")),
                 pou("Baz"))
    assert made.export()["ok"]
    return made


def code_of(bench, name):
    return [o for o in bench.tree.get_children(recursive=True)
            if o.get_name() == name][0].textual_implementation.text


def test_the_import_is_refused_naming_every_conflicted_file(bench):
    bench.edit("A/Foo.st", u"x := 1;", CONFLICT)
    bench.edit("Baz.st", u"x := 1;", CONFLICT)
    bench.edit("A/Bar.st", u"x := 1;", u"x := 9;")

    result = bench.import_()

    assert result["ok"] is False
    assert sorted(result["data"]["conflicted"]) == ["A/Foo.st", "Baz.st"]
    assert "A/Foo.st" in result["summary"] and "Baz.st" in result["summary"]
    # Nothing at all is applied, not even the file that was fine.
    assert code_of(bench, "Foo") == u"x := 1;"
    assert code_of(bench, "Bar") == u"x := 1;"


def test_a_file_without_markers_imports(bench):
    bench.edit("A/Foo.st", u"x := 1;",
               u"s := '<<<<<<< HEAD'; (* >>>>>>> *)")

    result = bench.import_()

    assert result["ok"] is True and result["data"]["updated"] == 1
    assert code_of(bench, "Foo") == u"s := '<<<<<<< HEAD'; (* >>>>>>> *)"


def test_a_new_file_mid_merge_is_refused_too(bench):
    bench.write("A/New.st", u"FUNCTION_BLOCK New\nVAR\nEND_VAR\n"
                u"// === IMPLEMENTATION ===\n" + CONFLICT)

    result = bench.import_()

    assert result["ok"] is False and result["data"]["conflicted"] == ["A/New.st"]
    assert "New" not in [o.get_name()
                         for o in bench.tree.get_children(recursive=True)]
