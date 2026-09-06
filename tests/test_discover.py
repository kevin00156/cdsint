# -*- coding: utf-8 -*-
"""discover is what you run when export dropped an object and said nothing.

An object whose type GUID is in no kind's alias list is skipped by
classify_object and counted nowhere, so the only way to find it is to walk
the tree and name the GUIDs nothing claimed. That answer is worthless if the
caller has to read `data` to learn that it needs to read `data`, so an
unknown GUID also makes the run not ok (SPEC D13).
"""
import sys

import pytest

from engine import entry_discover


class Node(object):
    """One object in the tree, with the four attributes discover reads."""

    def __init__(self, name, type_guid, parent=None):
        self._name = name
        self.type = type_guid
        self.guid = "guid-" + name
        self.parent = parent

    def get_name(self):
        return self._name


class Refusing(Node):
    """Its plugin is not installed, so reading .type raises (SPEC D13)."""

    @property
    def type(self):
        raise SystemError("The type guid of type IUnknownObject is not "
                          "available. Maybe a missing plugin?")

    @type.setter
    def type(self, value):
        pass


class Info(object):
    def __init__(self, values):
        self.values = values


class Project(object):
    def __init__(self, values, objects):
        self._values = values
        self._objects = objects
        self.path = "Fake.project"

    def get_project_info(self):
        return Info(self._values)

    def get_children(self, recursive=False):
        return list(self._objects)

    def get_name(self):
        return "FakeProject"


class Projects(object):
    def __init__(self, primary):
        self.primary = primary


class DeafUI(object):
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class DeafSystem(object):
    ui = DeafUI()


@pytest.fixture
def run(monkeypatch, tmp_path):
    """discover_project over a tree the test hands it."""
    discover = entry_discover
    monkeypatch.setattr(discover, "system", DeafSystem(), raising=False)

    def go(objects):
        project = Project({"cds-sync-folder": str(tmp_path)}, objects)
        projects = Projects(project)
        monkeypatch.setattr(discover, "projects", projects, raising=False)
        return discover.discover_project(projects)
    return go


def guid_for(kind):
    return sys.modules["engine.codesys_constants"].TYPE_GUIDS[kind]


def test_a_tree_it_recognises_end_to_end_is_ok(run):
    result = run([Node("MC_Main", guid_for("pou")),
                  Node("Types", guid_for("folder")),
                  Node("GVL", guid_for("gvl"))])

    assert result["ok"] is True
    assert result["data"]["total"] == 3
    assert result["data"]["unknown"] == []
    assert result["data"]["by_kind"] == {"pou": 1, "folder": 1, "gvl": 1}


def test_a_guid_no_kind_claims_is_named_and_the_run_is_not_ok(run):
    stranger = "0f0e0d0c-0b0a-0908-0706-050403020100"

    result = run([Node("MC_Main", guid_for("pou")),
                  Node("Sffe4717cHPS_1", stranger)])

    assert result["ok"] is False
    assert result["data"]["unknown"] == [{"name": "Sffe4717cHPS_1",
                                          "guid": stranger}]
    assert "Sffe4717cHPS_1" in result["summary"]
    assert stranger in result["summary"]


def test_the_unknown_guid_reaches_the_person_reading_stdout(run, capsys):
    # The fix is a JSON edit, and somebody who has not read the source has no
    # way to know that.
    run([Node("Sffe4717cHPS_1", "0f0e0d0c-0b0a-0908-0706-050403020100")])

    printed = capsys.readouterr().out
    assert "profiles/default.json" in printed
    assert "guid_aliases" in printed


def test_an_object_the_ide_will_not_describe_is_named_not_thrown(run):
    result = run([Node("MC_Main", guid_for("pou")),
                  Refusing("Sffe4717cHPS_1", None)])

    assert result["ok"] is False
    assert result["data"]["failed_objects"] == ["Sffe4717cHPS_1"]
    assert result["data"]["total"] == 2


def test_a_child_is_printed_under_its_parent(run, capsys):
    folder = Node("Types", guid_for("folder"))
    run([folder, Node("ST_Point", guid_for("dut"), parent=folder)])

    # load_base_dir logs to stdout as well, so read only the tree.
    lines = [line for line in capsys.readouterr().out.splitlines()
             if "|--" in line]
    assert lines == ["|-- Types (folder)", "  |-- ST_Point (dut)"]


def test_an_empty_project_is_ok_and_says_so(run):
    result = run([])

    assert result["ok"] is True
    assert result["data"]["total"] == 0
    assert result["data"]["by_kind"] == {}


def test_no_project_open_is_a_result_not_a_crash(monkeypatch):
    discover = entry_discover
    monkeypatch.setattr(discover, "system", DeafSystem(), raising=False)
    monkeypatch.setattr(discover, "projects", None, raising=False)

    result = discover.discover_project(Projects(None))

    assert result["ok"] is False and result["summary"]
