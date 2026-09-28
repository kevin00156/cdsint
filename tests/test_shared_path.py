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
