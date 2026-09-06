# -*- coding: utf-8 -*-
"""Reading a property off an IDE object, and what happens when it refuses.

Four engine modules used to carry a private version of each of these reads,
and the versions disagreed about the interesting half: whether an object that
will not answer gets recorded by name (SPEC D13) or merely logged. These tests
pin the answer down, because the difference only shows on the day something is
actually broken -- which is the day nobody is reading the log.
"""
import pytest

from engine import ide_read, unhandled
from tests.fakes import Node


class Sulking(object):
    """An object whose plugin is missing: every read raises."""

    def __init__(self, name="Sulking"):
        self._name = name

    def get_name(self):
        return self._name

    def _raise(self):
        raise RuntimeError("no plugin for this object")

    guid = property(lambda self: self._raise())
    type = property(lambda self: self._raise())
    parent = property(lambda self: self._raise())

    def get_children(self):
        self._raise()


@pytest.fixture(autouse=True)
def empty_register():
    unhandled.start()
    yield
    unhandled.start()


class TestReadsThatWork:
    def test_guid_of_reads_the_guid(self):
        assert ide_read.guid_of(Node("Main", "t")) == "guid-Main"

    def test_kind_of_maps_the_type_guid_to_a_kind(self):
        from engine.codesys_constants import TYPE_GUIDS
        assert ide_read.kind_of(Node("Main", TYPE_GUIDS["pou"])) == "pou"

    def test_parent_of_reads_the_parent(self):
        child = Node("Child", "t")
        parent = Node("Parent", "t", children=[child])
        assert ide_read.parent_of(child) is parent

    def test_parent_of_the_root_is_none_and_is_not_a_failure(self):
        """A missing parent is the top of the tree, not an object refusing."""
        assert ide_read.parent_of(Node("Root", "t")) is None
        assert unhandled.names() == []

    def test_children_of_lists_the_children(self):
        child = Node("Child", "t")
        assert ide_read.children_of(Node("P", "t", children=[child])) == [child]

    def test_name_of_is_the_registers_own(self):
        """One implementation, re-exported -- not a second copy."""
        assert ide_read.name_of is unhandled.name_of


class TestTheUpwardReadsStaySilent:
    """The project root ends every upward walk by raising rather than by
    answering None, and nothing can tell that apart from a missing plugin.

    Recording it put the project in the register three times per run and
    turned a clean export of 229 objects into a failed one -- measured on
    CODESYS 3.5.21.40 while this ticket was being built.
    """

    def test_guid_of_answers_none_without_a_word(self):
        assert ide_read.guid_of(Sulking()) is None
        assert unhandled.names() == []

    def test_parent_of_answers_none_without_a_word(self):
        assert ide_read.parent_of(Sulking()) is None
        assert unhandled.names() == []


class TestTheDownwardReadsRecord:
    """These walk into the tree, so a node that will not answer is a node
    whose contents are missing from the result. That gets a name (D13)."""

    def test_kind_of_records_and_returns_none(self):
        assert ide_read.kind_of(Sulking()) is None
        assert unhandled.names() == ["Sulking"]

    def test_children_of_records_and_returns_empty(self):
        """The one that matters most: a node that will not list its children
        looks exactly like a leaf from the caller's side."""
        assert ide_read.children_of(Sulking()) == []
        assert unhandled.names() == ["Sulking"]

    def test_an_empty_guid_is_no_guid(self):
        """"" would be a cache key every object without a GUID shares."""
        blank = Node("Blank", "t")
        blank.guid = ""
        assert ide_read.guid_of(blank) is None


class TestQuickHashRefusesToGuess:
    """A property whose accessors cannot be read has no quick hash.

    It used to have one: the read was swallowed and the hash was computed as
    if GET and SET were empty. The previous run had computed it the same way,
    so the two matched, the cache said "identical", and the export skipped a
    property nobody could read (SPEC 6.1, PRINCIPLES 6).
    """

    def test_none_rather_than_a_hash_of_nothing(self):
        from engine import codesys_utils
        from engine.codesys_constants import TYPE_GUIDS

        class Deaf(object):
            type = TYPE_GUIDS["property"]
            has_textual_declaration = True

            def get_name(self):
                return "Speed"

            @property
            def textual_declaration(self):
                class Text(object):
                    text = "PROPERTY Speed : INT"
                return Text()

            def get_children(self):
                raise RuntimeError("no plugin for the accessors")

        assert codesys_utils.get_quick_ide_hash(Deaf(), is_xml=False) is None
        assert unhandled.names() == ["Speed"]
