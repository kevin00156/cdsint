# -*- coding: utf-8 -*-
"""A .st import cannot read is a failed import of that file, by name.

parse_st_file printed the error and answered (None, None); the update read
that as "nothing to change" and the run reported success with the IDE as it
was. The file here is saved in cp1252, as a German Windows editor does, so
it is not UTF-8 (PRINCIPLES 6, SPEC D13).
"""
import pytest

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
