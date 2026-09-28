# -*- coding: utf-8 -*-
"""Two objects that resolve to one file are both named, not merged.

An application inside another adds no folder to the path, so a POU in each
lands on the same file. Export wrote both into it, the second over the
first, and compare kept whichever object it met last; either way one POU
silently stood for two (SPEC D13).
"""
import pytest

from engine import unhandled
from tests.sync_bench import Bench, Item, pou


@pytest.fixture
def bench(monkeypatch, tmp_path):
    inner = pou("Foo", u"inner := 1;")
    inner.guid = "guid-inner-Foo"
    return Bench(monkeypatch, tmp_path, Item("App1", "application", [
        pou("Foo", u"outer := 1;"), Item("App2", "application", [inner])]))


def test_export_names_both_and_does_not_let_one_overwrite_the_other(bench):
    result = bench.export()

    assert result["ok"] is False
    assert result["data"]["failed_objects"] == ["Foo", "Foo"]
    assert u"outer := 1;" in bench.read("App1/Foo.st")


def test_compare_names_both_and_compares_neither(bench):
    bench.export()
    unhandled.start()

    found = bench.compare()

    assert unhandled.names() == ["Foo", "Foo"]
    assert found["different"] == [] and found["new_on_disk"] == []


BAR = u"FUNCTION_BLOCK Bar\nVAR\nEND_VAR\n\n// === IMPLEMENTATION ===\ny := 2;"


def test_a_shared_file_does_not_stop_a_new_file_being_created(bench):
    # The pair went in the register as objects this run could not handle,
    # and the import gate read that as "some file may belong to one of
    # them": nothing on disk was ever created while the pair existed.
    bench.export()
    bench.write("App1/Bar.st", BAR)
    app1 = bench.tree.get_children()[0]
    made = []

    def create_pou(name, kind):
        made.append(pou(name, u""))
        made[-1].owner, made[-1].parent = app1._children, app1
        app1._children.append(made[-1])
        return made[-1]
    app1.create_pou = create_pou
    app1.create_child = create_pou

    result = bench.import_()

    assert result["data"]["created"] == 1 and made[0].get_name() == "Bar"


def test_a_shared_file_does_not_stop_the_orphan_sweep(monkeypatch, tmp_path):
    inner = pou("Foo", u"inner := 1;")
    inner.guid = "guid-inner-Foo"
    baz = pou("Baz")
    bench = Bench(monkeypatch, tmp_path, Item("App1", "application", [
        pou("Foo", u"outer := 1;"), baz, Item("App2", "application",
                                              [inner])]))
    bench.export()
    baz._name = "Baz2"

    result = bench.export(auto_delete_orphans=True)

    assert result["data"]["removed"] == 1
    assert "App1/Baz.st" not in bench.files()
