# -*- coding: utf-8 -*-
"""A compare run twice says the same thing twice.

Compare saved folder hashes built from what the IDE holds now, next to
per-object entries that still described the last sync. The second compare's
folder check then matched, its fast path trusted the disk's unchanged
timestamp, and an edit made in the IDE vanished from the report. An XML
object, which has no quick hash, borrowed its cached one for the folder hash
and vanished the same way on the first compare after its entry was written.
"""
import pytest

from engine import change_detect, classify
from engine.codesys_constants import TYPE_GUIDS
from tests.sync_bench import Bench, folder, pou, Item

VISU = u'<Object>\n  <Body>%s</Body>\n</Object>\n'


@pytest.fixture
def bench(monkeypatch, tmp_path):
    made = Bench(monkeypatch, tmp_path, folder("A", pou("Foo"), pou("Bar")))
    assert made.export()["ok"]
    return made


def different(bench):
    return sorted(item["path"] for item in bench.compare()["different"])


def test_an_ide_edit_is_still_different_on_the_second_compare(bench):
    foo = bench.tree.get_children()[0].get_children()[0]
    foo.textual_implementation.text = u"x := 999;"

    assert different(bench) == ["A/Foo.st"]
    assert different(bench) == ["A/Foo.st"]


@pytest.fixture
def with_a_visu(bench, monkeypatch):
    """An XML object in the same folder, as compare sees one: its own path
    and its native XML, which the fake reads off the object."""
    visu = Item("V", "folder")
    visu.xml = VISU % u"one"
    bench.tree.get_children()[0]._children.append(visu)
    bench.write("A/V.visu.xml", visu.xml)
    resolve, content = change_detect.resolve_object, change_detect.get_ide_content

    def resolve_visu(obj, guid, types, export_xml, project):
        if obj is visu:
            return classify.Resolved(TYPE_GUIDS["visu_manager"], True,
                                     "A/V.visu.xml", None, "miss")
        return resolve(obj, guid, types, export_xml, project)

    def read_visu(obj, is_xml, accessors, project, can_have_impl=False):
        if obj is visu:
            return obj.xml, {}
        return content(obj, is_xml, accessors, project, can_have_impl)

    monkeypatch.setattr(change_detect, "resolve_object", resolve_visu)
    monkeypatch.setattr(change_detect, "get_ide_content", read_visu)
    return visu


def test_an_ide_edit_to_an_xml_object_is_seen(bench, with_a_visu):
    assert different(bench) == []
    assert different(bench) == []

    with_a_visu.xml = VISU % u"two"

    assert different(bench) == ["A/V.visu.xml"]
