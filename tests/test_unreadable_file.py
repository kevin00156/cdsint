# -*- coding: utf-8 -*-
"""A .st that is not UTF-8 is a failed import of that file, by name, and
compare says why it lists it.

parse_st_file printed the error and answered (None, None); the update read
that as "nothing to change" and the run reported success with the IDE as it
was. The file here is saved in cp1252, as a German Windows editor does, so
it is not UTF-8 (PRINCIPLES 6, SPEC D13).
"""
import pytest

from cds.core import settings
from engine import entry_compare, unhandled
from tests.fakes import DeafSystem
from tests.sync_bench import Bench, folder, pou


@pytest.fixture
def bench(monkeypatch, tmp_path):
    made = Bench(monkeypatch, tmp_path, folder("A", pou("Foo")))
    assert made.export()["ok"]
    return made


def cp1252(bench, rel):
    text = bench.read(rel).replace(u"x := 1;", u"x := 7; // Temperatur \xe4")
    bench.write(rel, u"")
    with open(bench.path(rel), "wb") as handle:
        handle.write(text.encode("cp1252"))


def test_an_unreadable_file_fails_the_import_by_name(bench):
    cp1252(bench, "A/Foo.st")

    result = bench.import_()

    assert result["ok"] is False
    assert result["data"]["failed"] == 1
    assert result["data"]["failed_objects"] == ["A/Foo.st"]


def test_an_unreadable_property_fails_the_same_way(tmp_path):
    from engine.managers_pou import PropertyManager
    path = tmp_path / "P.st"
    path.write_bytes(u"PROPERTY P : INT // \xe4\n".encode("cp1252"))

    with pytest.raises(ValueError):
        PropertyManager().update(object(), str(path))


def compare(bench, monkeypatch):
    monkeypatch.setattr(entry_compare, "system", DeafSystem(), raising=False)
    return entry_compare.compare_project(str(bench.sync), settings.resolve({}),
                                         bench.projects)


def test_compare_says_the_file_is_not_utf8(bench, monkeypatch, capsys):
    # A GVL saved from an ANSI editor on a Chinese-locale PC: compare listed
    # it as changed and never said why, and import then refused it.
    cp1252(bench, "A/Foo.st")

    result = compare(bench, monkeypatch)

    row = [r for r in result["data"]["changes"] if r["path"] == "A/Foo.st"][0]
    assert row["state"] == "changed"
    assert row["problem"].startswith("not UTF-8 text")
    listed = [line for line in capsys.readouterr().out.splitlines()
              if line.startswith("  M  A/Foo.st")]
    assert listed and all("not UTF-8 text" in line for line in listed)


def test_what_counts_as_different_is_unchanged(bench, monkeypatch):
    cp1252(bench, "A/Foo.st")

    result = compare(bench, monkeypatch)

    assert result["ok"] is True
    assert result["data"]["different"] == 1


def test_an_ordinary_edit_carries_no_problem(bench, monkeypatch):
    bench.edit("A/Foo.st", u"x := 1;", u"x := 2;")

    rows = compare(bench, monkeypatch)["data"]["changes"]

    assert rows == [{"name": "Foo", "path": "A/Foo.st", "state": "changed"}]


def test_import_refuses_it_in_the_same_words(bench, monkeypatch):
    cp1252(bench, "A/Foo.st")
    said = compare(bench, monkeypatch)["data"]["changes"][0]["problem"]

    bench.import_()

    assert [r["reason"] for r in unhandled.records()] == [said]
