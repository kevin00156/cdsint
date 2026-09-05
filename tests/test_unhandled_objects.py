# -*- coding: utf-8 -*-
"""An object the IDE will not describe must be named, not thrown.

Opening a project in another vendor's IDE leaves objects whose plugin is not
installed, and reading .type off one of those raises. classify_object has
five call sites; four wrapped it and one did not, so export survived while
compare and import lost all 229 objects to a traceback. The fix is one place
(engine/unhandled.py) and one rule: name it in `data`, and the command is
not ok (SPEC D13).
"""
import sys

import pytest

from engine import unhandled


class Missing(object):
    """An object whose plugin is not installed. Every attribute raises."""

    def __init__(self, name="Sffe4717cHPS_1"):
        self._name = name

    @property
    def type(self):
        raise SystemError("The type guid of type IUnknownObject is not "
                          "available. Maybe a missing plugin?")

    def get_name(self):
        return self._name

    def get_children(self, recursive=False):
        return []


class Nameless(Missing):
    """The same, but it will not even say what it is called."""

    def get_name(self):
        raise SystemError("The object GUID is not valid.")


@pytest.fixture(autouse=True)
def fresh():
    unhandled.start()
    yield
    unhandled.start()


# --- the register ----------------------------------------------------------

def test_a_noted_object_is_remembered_by_name_and_reason():
    unhandled.note(Missing("MC_BasicControl"), "missing plugin")
    assert unhandled.names() == ["MC_BasicControl"]
    assert unhandled.records()[0]["reason"] == "missing plugin"


def test_an_object_that_will_not_say_its_name_still_gets_a_line():
    unhandled.note(Nameless(), "missing plugin")
    assert len(unhandled.names()) == 1
    assert unhandled.names()[0]  # a sentence, not an exception


def test_a_path_string_is_taken_as_the_name():
    # Some failures happen after the object is gone, with only its path left.
    unhandled.note("Function Blocks/MC_Main.st", "could not be created")
    assert unhandled.names() == ["Function Blocks/MC_Main.st"]


def test_starting_a_command_forgets_the_previous_one():
    unhandled.note("A", "x")
    unhandled.start()
    assert unhandled.names() == [] and not unhandled.any_so_far()


def test_the_summary_names_them_and_stops_at_ten():
    for i in range(14):
        unhandled.note("Object%d" % i, "x")
    line = unhandled.summary()
    assert line.startswith("14 object(s) could not be handled")
    assert "Object0" in line and "Object9" in line
    assert "and 4 more" in line and "Object10" not in line


# --- the one place that catches it -----------------------------------------

@pytest.fixture(scope="module")
def managers(load_engine):
    load_engine("codesys_constants")
    load_engine("codesys_utils")
    return load_engine("codesys_managers")


def test_classify_object_names_it_instead_of_raising(managers):
    effective_type, is_xml, should_skip = managers.classify_object(Missing())
    assert should_skip is True
    assert unhandled.names() == ["Sffe4717cHPS_1"]


def test_classify_object_still_works_on_an_object_it_can_read(managers):
    constants = sys.modules["engine.codesys_constants"]

    class Pou(object):
        type = constants.TYPE_GUIDS["pou"]
        parent = None

        def get_name(self):
            return "MC_Main"

    effective_type, is_xml, should_skip = managers.classify_object(Pou())
    assert should_skip is False
    assert not unhandled.any_so_far()


# --- what the three commands do with one ------------------------------------

class Info(object):
    def __init__(self, values):
        self.values = values


class Project(object):
    """A project holding exactly one object the IDE will not describe."""

    def __init__(self, values, children, path):
        self._values = values
        self._children = children
        self.path = path

    def get_project_info(self):
        return Info(self._values)

    def get_children(self, recursive=False):
        return list(self._children)

    def get_name(self):
        return "FakeProject"

    def save(self):
        pass


class Projects(object):
    def __init__(self, primary):
        self.primary = primary


class DeafUI(object):
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class DeafSystem(object):
    ui = DeafUI()


@pytest.fixture
def one_bad_object(load_engine, monkeypatch, tmp_path):
    """The three entry bodies, lent an IDE holding one unreadable object.

    Lent the same way engine/entry.py lends the IDE's globals to a body when
    the menu presses it — the bodies read `projects` and `system` as plain
    globals of their own module.
    """
    for dep in ("codesys_constants", "codesys_utils", "codesys_managers",
                "codesys_compare_engine"):
        load_engine(dep)
    bodies = [load_engine(name) for name in
              ("entry_export", "entry_compare", "entry_import")]

    sync = str(tmp_path)
    # cds-sync-version matches, so import does not stop at the version dialog
    # on its way to the object; that dialog is codesys_ui, which needs clr.
    version = sys.modules["engine.codesys_constants"].SCRIPT_VERSION
    project = Project({"cds-sync-folder": sync, "cds-sync-version": version},
                      [Missing()], str(tmp_path / "Fake.project"))
    projects = Projects(project)
    for body in bodies:
        monkeypatch.setattr(body, "projects", projects, raising=False)
        monkeypatch.setattr(body, "system", DeafSystem(), raising=False)
    export, compare, imp = bodies
    # An empty sync folder is refused before any tree walking happens
    # (tests/test_empty_sync_folder.py owns that rule); these tests are about
    # what the walk does with an object it cannot read. Putting a real .st
    # here instead would give the import something to create, and the
    # confirmation dialog for it lives in codesys_ui, which needs clr.
    monkeypatch.setattr(imp, "has_st_files", lambda base_dir: True)
    return {
        "export": lambda: export.export_project(sync, projects),
        "compare": lambda: compare.compare_project(projects),
        "import": lambda: imp.import_project(projects),
    }


@pytest.mark.parametrize("command", ("export", "compare", "import"))
def test_a_command_names_the_object_and_is_not_ok(one_bad_object, command):
    # No traceback, a verdict of False, and a name the reader can go and
    # look up in the IDE — all three, for every command that walks the tree.
    result = one_bad_object[command]()
    assert result["ok"] is False
    assert result["data"]["failed_objects"] == ["Sffe4717cHPS_1"]
    assert "Sffe4717cHPS_1" in result["summary"]


def test_export_does_not_delete_orphans_it_cannot_account_for(one_bad_object,
                                                              tmp_path):
    # The unreadable object has no path, so its .st looks like an orphan.
    # Deleting it would throw away a file the project still needs, and the
    # run has no way to tell which file that is.
    orphan = tmp_path / "Somebody.st"
    orphan.write_text(u"FUNCTION_BLOCK Somebody\n", encoding="utf-8")
    result = one_bad_object["export"]()
    assert orphan.exists()
    assert result["data"]["removed"] == 0
