# -*- coding: utf-8 -*-
"""One classification, asked the same way by export and by compare.

This is the agreement the whole comparison rests on. When export refuses to
write an object and compare still looks for its file, pass 2 reads the missing
file as an orphan and the next import deletes the object from the IDE. The two
used to agree by carrying the same thirty lines twice, with a comment in one
copy asking whoever edited it to remember the other.
"""
import pytest

from engine import classify, unhandled
from engine.codesys_constants import TYPE_GUIDS
from tests.fakes import Node


@pytest.fixture(autouse=True)
def empty_register():
    unhandled.start()
    yield
    unhandled.start()


def a_pou(name="Main"):
    return Node(name, TYPE_GUIDS["pou"])


class TestBothSidesGetTheSameAnswer:
    """export and compare now call one function, so the test that matters is
    that the function is the whole answer: same object and same cache in,
    same classification, same path and same verdict out."""

    def test_the_same_object_resolves_the_same_way_twice(self):
        obj = a_pou()
        first = classify.resolve_object(obj, {}, export_xml=False)
        second = classify.resolve_object(obj, {}, export_xml=False)
        assert first[:4] == second[:4]

    def test_a_cached_path_and_a_fresh_classification_agree(self):
        """The cache is a shortcut, not a second opinion. If they disagreed,
        an export and a compare of the same tree would use different paths."""
        obj = a_pou()
        fresh = classify.resolve_object(obj, {}, export_xml=False)
        cache = {"guid-Main": (fresh.effective_type, fresh.is_xml,
                               fresh.rel_path)}
        cached = classify.resolve_object(obj, cache, export_xml=False)
        assert cached.cache == "hit"
        assert cached[:4] == fresh[:4]

    def test_a_moved_object_is_reclassified_rather_than_half_trusted(self):
        obj = a_pou()
        stale = {"guid-Main": (TYPE_GUIDS["pou"], False, "Somewhere/Else.st")}
        decided = classify.resolve_object(obj, stale, export_xml=False)
        assert decided.cache == "invalidated"
        assert decided.rel_path != "Somewhere/Else.st"

    def test_a_cached_skip_is_never_trusted(self):
        """The set of supported kinds changes between versions. A once-skipped
        object that stayed skipped would be buried for good -- and on the
        compare side its file would be deleted as a false orphan."""
        obj = a_pou()
        skipped = {"guid-Main": (TYPE_GUIDS["pou"], False, None)}
        decided = classify.resolve_object(obj, skipped, export_xml=False)
        assert decided.cache == "miss"
        assert decided.rel_path


class TestTheGates:
    def test_a_supported_object_gets_a_path_and_no_skip_reason(self):
        decided = classify.resolve_object(a_pou(), {}, export_xml=False)
        assert decided.skip_reason is None
        assert decided.rel_path.endswith(".st")

    def test_an_xml_kind_is_gated_when_export_xml_is_off(self):
        obj = Node("Library Manager", TYPE_GUIDS["library_manager"])
        decided = classify.resolve_object(obj, {}, export_xml=False)
        assert decided.skip_reason == classify.SKIP_XML_GATE

    def test_the_same_object_passes_when_export_xml_is_on(self):
        obj = Node("Library Manager", TYPE_GUIDS["library_manager"])
        decided = classify.resolve_object(obj, {}, export_xml=True)
        assert decided.skip_reason is None

    def test_a_task_config_is_written_either_way(self):
        """Project structure, not one of the optional extras the flag is for."""
        obj = Node("Task configuration", TYPE_GUIDS["task_config"])
        for export_xml in (True, False):
            decided = classify.resolve_object(obj, {}, export_xml=export_xml)
            assert decided.skip_reason is None

    def test_an_unsupported_kind_has_no_path_at_all(self):
        decided = classify.resolve_object(Node("Odd", "not-a-known-guid"), {},
                                          export_xml=True)
        assert decided.skip_reason == classify.SKIP_UNSUPPORTED
        assert decided.rel_path is None


class TestAccessorCollection:
    def test_a_property_contributes_its_get_and_set(self):
        get = Node("Get", TYPE_GUIDS["property_accessor"])
        put = Node("Set", TYPE_GUIDS["property_accessor"])
        prop = Node("Speed", TYPE_GUIDS["property"], children=[get, put])
        found = {}
        classify.collect_accessors(prop, TYPE_GUIDS["property"], found)
        assert found["guid-Speed"] == {"get": get, "set": put}

    def test_anything_that_is_not_a_property_contributes_nothing(self):
        found = {}
        classify.collect_accessors(a_pou(), TYPE_GUIDS["pou"], found)
        assert found == {}

    def test_a_property_that_will_not_list_its_children_is_named(self):
        """An empty pair means the file is built as if GET and SET were empty.
        That is a guess, so the object goes in the register (SPEC D13)."""
        class Sulking(Node):
            def get_children(self, recursive=False):
                raise RuntimeError("no plugin")

        found = {}
        classify.collect_accessors(Sulking("Speed", TYPE_GUIDS["property"]),
                                   TYPE_GUIDS["property"], found)
        assert found["guid-Speed"] == {"get": None, "set": None}
        assert unhandled.names() == ["Speed"]
