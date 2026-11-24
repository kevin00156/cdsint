# -*- coding: utf-8 -*-
"""A second persistent variable list is refused before CODESYS is asked.

CODESYS answers a second one in an application with a modal dialog, and a
headless import has nobody to close it: the command hung to its timeout.
"""
from engine import unhandled
from tests.sync_bench import Bench, Item, folder

PERSISTENT = u"VAR_GLOBAL PERSISTENT RETAIN\n    g_count : INT;\nEND_VAR"
SECOND = u"//% cds-text-sync.kind=persistent_gvl\n\n" + PERSISTENT + u"\n"


def persistent(name):
    return Item(name, "persistent_gvl", decl=PERSISTENT)


def app(name, *children):
    """An application whose create_child records what it was asked for."""
    made = Item(name, "application", list(children))
    made.asked = []

    def create_child(child_name, type_guid):
        made.asked.append(child_name)
        child = Item(child_name, "persistent_gvl", decl=u"")
        child.owner, child.parent = made._children, made
        made._children.append(child)
        return child
    made.create_child = create_child
    return made


def bench_of(monkeypatch, tmp_path, *apps):
    made = Bench(monkeypatch, tmp_path, Item("PLC", "device", list(apps)))
    assert made.export()["ok"]
    unhandled.start()
    return made


def test_a_second_list_in_one_application_is_refused_by_name(
        monkeypatch, tmp_path):
    target = app("App", folder("Retain", persistent("PersistentVars")))
    bench = bench_of(monkeypatch, tmp_path, target)
    bench.write("PLC/App/MoreVars.st", SECOND)

    result = bench.import_()

    assert target.asked == []
    assert result["ok"] is False
    assert result["data"]["created"] == 0
    [record] = unhandled.records()
    assert record["name"] == "PLC/App/MoreVars.st"
    assert "'MoreVars'" in record["reason"]
    assert "'PersistentVars'" in record["reason"]


def test_the_first_list_in_an_application_is_created(monkeypatch, tmp_path):
    target = app("App")
    bench = bench_of(monkeypatch, tmp_path, target)
    bench.write("PLC/App/PersistentVars.st", SECOND)

    result = bench.import_()

    assert target.asked == ["PersistentVars"]
    assert result["ok"] is True and result["data"]["created"] == 1


def test_another_applications_list_is_not_this_ones(monkeypatch, tmp_path):
    first = app("App1", persistent("PersistentVars"))
    second = app("App2")
    bench = bench_of(monkeypatch, tmp_path, first, second)
    bench.write("PLC/App2/PersistentVars.st", SECOND)

    result = bench.import_()

    assert second.asked == ["PersistentVars"]
    assert result["ok"] is True and result["data"]["created"] == 1


def test_a_child_applications_list_is_not_its_parents(monkeypatch, tmp_path):
    child = app("Child", persistent("PersistentVars"))
    parent = app("App", child)
    bench = bench_of(monkeypatch, tmp_path, parent)
    bench.write("PLC/App/AppVars.st", SECOND)

    result = bench.import_()

    assert parent.asked == ["AppVars"]
    assert result["ok"] is True

