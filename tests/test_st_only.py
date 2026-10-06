# -*- coding: utf-8 -*-
"""Code is synced as Structured Text and nothing else (SPEC 4.5).

A POU, method or action with no textual implementation -- an abstract method,
or a graphical body nobody here uses -- is a declaration-only .st. Native XML
for code is what an older export left behind, and importing it is refused by
name: the IDE answered it with a modal "Select Implementation Language" that
froze a headless run and, when a person answered it, deleted ABSTRACT.
"""
import pytest

from engine import import_gates, import_items, object_content, unhandled


def refused(rel):
    tally = import_items._Tally()
    unhandled.start()
    return import_gates.refused_by_path({"path": rel}, tally), tally


@pytest.mark.parametrize("rel", [
    "App/StateMachine/BaseStateMachine/Init.method.xml",
    "App/StateMachine/BaseStateMachine/Init.method_alt.xml",
    "App/Programs/Ladder.pou_xml.xml",
    "App/Programs/Ladder/Ladder.Step.action.xml",
])
def test_code_as_native_xml_is_refused_by_path(rel):
    was_refused, tally = refused(rel)
    assert was_refused and tally.failed == 1
    assert [r["name"] for r in unhandled.records()] == [rel]
    assert "Run export" in unhandled.records()[0]["reason"]


@pytest.mark.parametrize("rel", [
    "App/Task Configuration.task_config.xml",
    "App/Programs/PLC_PRG.st",
    "App/StateMachine/BaseStateMachine.Init.st",
])
def test_everything_else_is_not(rel):
    was_refused, tally = refused(rel)
    assert not was_refused and tally.failed == 0


class TextDocument(object):
    def __init__(self, text=u""):
        self.text = text


class AbstractMethod(object):
    """What the IDE hands over for an abstract method: no implementation."""
    has_textual_declaration = True
    has_textual_implementation = False

    def __init__(self):
        self.textual_declaration = TextDocument(
            u"METHOD PROTECTED ABSTRACT Init : BOOL")

    def get_name(self):
        return "Init"


def test_code_with_nowhere_to_go_fails_by_name():
    with pytest.raises(RuntimeError, match="Init"):
        object_content.update_object_code(
            AbstractMethod(), u"METHOD PROTECTED Init : BOOL", u"Init := TRUE;")


@pytest.mark.parametrize("implementation", [None, u"", u"\n  \n"])
def test_an_empty_implementation_is_no_code(implementation):
    method = AbstractMethod()
    object_content.update_object_code(
        method, u"METHOD PROTECTED ABSTRACT Init : DINT", implementation)
    assert method.textual_declaration.text.endswith(u"DINT")


def test_an_object_whose_file_is_still_old_code_xml_is_not_deleted():
    # The old export wrote Init as XML; this one looks for
    # BaseStateMachine.Init.st, finds none, and calls the method an orphan.
    # Deleting it would take the method out of the project in the same
    # import that refuses the XML: a stale sync folder right after updating.
    xml = {"path": "App/SM/BaseStateMachine/Init.method.xml", "name": "Init"}
    orphan = {"path": "App/SM/BaseStateMachine.Init.st", "name": "Init",
              "is_orphan": True}
    stale = import_gates.stale_code_names([xml, orphan])
    assert import_gates.never_deleted(orphan, stale)
    other = {"path": "App/SM/BaseStateMachine.Stop.st", "name": "Stop",
             "is_orphan": True}
    assert not import_gates.never_deleted(other, stale)
