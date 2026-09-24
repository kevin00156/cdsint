# -*- coding: utf-8 -*-
"""Native XML import answers the overwrite question (engine/native_import.py).

Without a handler, import_native asks PromptImportConflict for every object
the project already has, and headless nobody can answer it, so every edited
native object failed to import. The handler itself is a .NET subclass and
only exists inside the IDE; these tests stand a fake in for it and check
what the engine does with it.
"""
import pytest

from engine import native_import, object_create, unhandled


class FakeHandler(object):
    """What replace_handler() hands out, minus the .NET base class."""

    def __init__(self):
        self.failures = []


class Target(object):
    """A project or container: records the import, answers with `result`.

    `fail` is a name the IDE reports trouble for, the way the real one calls
    progress() with an exception.
    """

    def __init__(self, result="ok", fail=None, children=()):
        self.result = result
        self.fail = fail
        self.children = list(children)
        self.calls = []

    def import_native(self, path, import_filter, handler):
        self.calls.append((path, import_filter, handler))
        if self.fail:
            handler.failures.append("%s: could not be imported" % self.fail)
        return self.result

    def get_children(self, recursive=False):
        return self.children

    def get_name(self):
        return "Application"


class Child(object):
    def __init__(self, name):
        self.name = name

    def get_name(self):
        return self.name


@pytest.fixture(autouse=True)
def fake_handler(monkeypatch):
    monkeypatch.setattr(native_import, "replace_handler", FakeHandler)
    unhandled.start()
    yield
    unhandled.start()


def test_the_import_carries_a_handler_and_no_filter():
    target = Target()

    assert native_import.import_native(target, "T.trace.xml") == "ok"

    (path, import_filter, handler), = target.calls
    assert path == "T.trace.xml"
    assert import_filter is None
    assert isinstance(handler, FakeHandler)


def test_a_failure_the_ide_reports_is_raised_with_its_name():
    with pytest.raises(RuntimeError, match="T_slot1: could not be imported"):
        native_import.import_native(Target(fail="T_slot1"), "T.trace.xml")


def test_an_errors_result_with_nothing_said_is_still_a_failure():
    with pytest.raises(RuntimeError, match="the IDE reported errors"):
        native_import.import_native(Target(result="errors"), "T.trace.xml")


def test_the_script_engine_assembly_is_found_by_name():
    class Assembly(object):
        def __init__(self, name):
            self.Name = name

        def GetName(self):
            return self

    wanted = Assembly("ScriptEngine3")

    assert native_import._loaded_assembly([Assembly("mscorlib"), wanted]) is wanted
    with pytest.raises(RuntimeError, match="ScriptEngine3 is not loaded"):
        native_import._loaded_assembly([Assembly("mscorlib")])


def _batch(container):
    item = ("Application/T_slot1.trace.xml", "T_slot1.trace.xml", "T_slot1",
            "f7aa3620-8073-4c91-b6ec-86ed9eb60303", False)
    return {container: [item]}


def _no_merge_needed(monkeypatch):
    monkeypatch.setattr(object_create, "merge_native_xmls",
                        lambda paths, out: True)


def test_an_edited_object_in_a_batch_counts_as_updated(monkeypatch):
    _no_merge_needed(monkeypatch)
    container = Target(children=[Child("T_slot1")])

    counts = object_create.batch_import_native_xmls_with_children(
        _batch(container), {}, project=None)

    assert counts == (1, 0, 0)
    assert len(container.calls) == 1
    assert unhandled.names() == []


def test_a_batch_the_ide_refuses_names_every_object_in_it(monkeypatch):
    _no_merge_needed(monkeypatch)
    container = Target(fail="T_slot1", children=[Child("T_slot1")])

    counts = object_create.batch_import_native_xmls_with_children(
        _batch(container), {}, project=None)

    assert counts == (0, 0, 1)
    assert unhandled.names() == ["T_slot1"]
