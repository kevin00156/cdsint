# -*- coding: utf-8 -*-
"""A file moved on disk moves its object on import, with its edit.

Compare detected the move and import threw it away: the moved file was on
neither the "different" nor the "new" list, so import said there was
nothing to do, and the next export put the file back where the IDE had it
and deleted the moved copy with the edit in it.
"""
import os

import pytest

from engine import unhandled
from tests.sync_bench import Bench, Item, folder, pou


@pytest.fixture
def bench(monkeypatch, tmp_path):
    made = Bench(monkeypatch, tmp_path, folder("A", pou("Foo")), folder("B"))
    assert made.export()["ok"]
    return made


def move_on_disk(bench, old, new, edit=None):
    text = bench.read(old)
    os.remove(bench.path(old))
    bench.write(new, text if edit is None else text.replace(*edit))


def foo(bench):
    return [o for o in bench.tree.get_children(recursive=True)
            if o.get_name() == "Foo"][0]


def test_the_object_follows_its_file_and_takes_the_edit(bench):
    move_on_disk(bench, "A/Foo.st", "B/Foo.st", (u"x := 1;", u"x := 42;"))

    result = bench.import_()

    assert result["ok"] is True and result["data"]["moved"] == 1
    assert "Moved: 1" in result["summary"]
    assert foo(bench).parent.get_name() == "B"
    assert foo(bench).textual_implementation.text == u"x := 42;"


def test_the_export_after_it_keeps_the_moved_file(bench):
    move_on_disk(bench, "A/Foo.st", "B/Foo.st", (u"x := 1;", u"x := 42;"))
    bench.import_()

    result = bench.export(auto_delete_orphans=True)

    assert bench.files() == ["B/Foo.st"]
    assert u"x := 42;" in bench.read("B/Foo.st")
    assert result["ok"] is True


def test_a_method_goes_with_its_pou_and_is_not_moved_on_its_own(
        monkeypatch, tmp_path):
    method = Item("Run", "method", decl=u"METHOD Run\nVAR\nEND_VAR",
                  impl=u"r := 1;")
    fb = pou("Foo")
    fb._children.append(method)
    method.parent, method.owner = fb, fb._children
    bench = Bench(monkeypatch, tmp_path, folder("A", fb), folder("B"))
    assert bench.export()["ok"]
    move_on_disk(bench, "A/Foo.st", "B/Foo.st")
    move_on_disk(bench, "A/Foo.Run.st", "B/Foo.Run.st")

    result = bench.import_()

    assert result["ok"] is True and result["data"]["moved"] == 1
    assert fb.parent.get_name() == "B" and method.parent is fb


def test_a_file_of_the_same_name_in_another_application_is_not_a_move(
        monkeypatch, tmp_path):
    old = pou("Foo")
    bench = Bench(monkeypatch, tmp_path, Item("App1", "application", [old]),
                  Item("App2", "application"))
    assert bench.export()["ok"]
    unhandled.start()
    move_on_disk(bench, "App1/Foo.st", "App2/Foo.st")

    found = bench.compare()

    assert found["moved"] == []
    assert [i["path"] for i in found["new_on_disk"]] == ["App2/Foo.st"]
    assert [i["path"] for i in found["new_in_ide"]] == ["App1/Foo.st"]


class Unreadable(Item):
    """An object whose plugin is missing: every read raises."""

    @property
    def guid(self):
        raise RuntimeError("plugin missing")

    @guid.setter
    def guid(self, value):
        pass


def test_a_run_that_could_not_read_every_object_moves_nothing(bench):
    # The unreadable object's own file could be the one that looks moved,
    # so the pairing is not evidence of anything.
    bench.tree.get_children()[1]._children.append(Unreadable("Ghost", "pou"))
    move_on_disk(bench, "A/Foo.st", "B/Foo.st")

    result = bench.import_()

    assert result["ok"] is False and result["data"]["moved"] == 0
    assert result["data"]["not_created"] == ["B/Foo.st"]
    assert foo(bench).parent.get_name() == "A"


def test_a_device_renamed_since_the_export_keeps_its_objects(
        monkeypatch, tmp_path):
    # The folder names the device the export saw, and the application check
    # read that name as another application: no object paired with its own
    # file, so import deleted every one of them and made them again.
    old = pou("Foo")
    device = Item("PLC_A", "device", [Item("Application", "application",
                                           [old])])
    bench = Bench(monkeypatch, tmp_path, device)
    assert bench.export()["ok"]
    unhandled.start()
    device._name = "PLC_B"
    bench.edit("PLC_A/Application/Foo.st", u"x := 1;", u"x := 42;")

    result = bench.import_()

    assert result["ok"] is True and result["data"]["deleted"] == 0
    assert old.removed is False
    assert old.textual_implementation.text == u"x := 42;"
