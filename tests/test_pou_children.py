# -*- coding: utf-8 -*-
"""A graphical POU's members come back after its XML import, or are named.

Importing a POU's native XML replaces it, and its methods, actions and
properties go with it. They are saved first and put back; every way that
could fail was a log line, so a member could vanish from the project while
the import reported success. Creation also went through create_object(),
which nothing else calls, instead of the creators POUManager uses.
"""
import pytest

from engine import classify, unhandled
from engine.codesys_constants import TYPE_GUIDS
from engine.pou_children import restore_pou_children, save_pou_children
from tests.sync_bench import Item


class Graphical(Item):
    """A POU as the IDE hands it back after the import: members it offers to
    create, recorded, and none of the old ones."""

    def __init__(self, name="Foo", creators=("create_method",)):
        Item.__init__(self, name, "pou")
        self.created = []
        for creator in creators:
            setattr(self, creator, self._maker(creator))

    def _maker(self, creator):
        kind = {"create_method": "method", "create_action": "action",
                "create_property": "property"}[creator]

        def make(name):
            member = Item(name, kind, decl=u"", impl=u"")
            if kind == "property":
                member.create_get_accessor = lambda: self._accessor(member, "Get")
            member.parent, member.owner = self, self._children
            self._children.append(member)
            self.created.append((creator, name))
            return member
        return make

    def _accessor(self, prop, name):
        made = Item(name, "folder", decl=u"", impl=u"")
        made.parent, made.owner = prop, prop._children
        prop._children.append(made)
        return made


@pytest.fixture
def managers():
    unhandled.start()
    yield classify.create_import_managers(None)
    unhandled.start()


def a_method():
    return {"name": "Run", "type_guid": TYPE_GUIDS["method"],
            "declaration": u"METHOD Run", "implementation": u"r := 1;",
            "accessors": {}}


def test_a_member_is_made_the_way_pou_manager_makes_it(managers):
    pou = Graphical()

    restore_pou_children(pou, [a_method()], managers, None)

    assert pou.created == [("create_method", "Run")]
    assert pou.get_children()[0].textual_implementation.text == u"r := 1;"
    assert unhandled.names() == []


def test_a_member_that_cannot_be_made_again_is_named(managers):
    pou = Graphical(creators=())

    restore_pou_children(pou, [a_method()], managers, None)

    assert unhandled.names() == ["Foo.Run"]


def test_a_propertys_accessors_come_back_with_it(managers):
    prop = Item("Speed", "property", decl=u"PROPERTY Speed : INT")
    get = Item("Get", "folder", decl=u"", impl=u"Speed := 7;")
    prop._children.append(get)
    get.parent = prop
    old = Item("Foo", "pou", [prop])
    saved = save_pou_children(old, None)
    pou = Graphical(creators=("create_property",))

    restore_pou_children(pou, saved, managers, None)

    [made] = pou.get_children()
    assert made.get_children()[0].textual_implementation.text == u"Speed := 7;"
    assert unhandled.names() == []
