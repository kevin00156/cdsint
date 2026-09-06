# -*- coding: utf-8 -*-
"""Tests that pin down how often the engine touches a live IDE object.

Every attribute read on a CODESYS script object crosses into .NET, and
profiling an unchanged export showed that cost dominating: the helpers here
were re-reading the same property several times per call. The tests assert
BEHAVIOUR is unchanged and that the number of reads dropped, because a
refactor that quietly reintroduces a double read looks fine in every other
test.
"""
import sys

import pytest

from tests.fakes import Project

from engine import codesys_managers, codesys_utils, entry_build, sync_cache


@pytest.fixture(scope="module")
def env():
    utils = codesys_utils
    managers = codesys_managers
    return utils, managers, sys.modules["engine.codesys_constants"].TYPE_GUIDS


class CountingObj(object):
    """Records every property access, the way the interop boundary charges."""

    def __init__(self, name="Obj", type_guid="t", parent=None, flags=None,
                 missing=()):
        self._name = name
        self._type = type_guid
        self._parent = parent
        self._flags = flags or {}
        self._missing = set(missing)
        self.reads = {}

    def _tick(self, what):
        self.reads[what] = self.reads.get(what, 0) + 1

    def __getattr__(self, item):
        # Only reached for names not set in __init__.
        if item in ("has_textual_declaration", "has_textual_implementation"):
            object.__getattribute__(self, "_tick")(item)
            flags = object.__getattribute__(self, "_flags")
            missing = object.__getattribute__(self, "_missing")
            if item in missing:
                raise AttributeError(item)
            return flags.get(item, False)
        raise AttributeError(item)

    @property
    def type(self):
        self._tick("type")
        return self._type

    @property
    def parent(self):
        self._tick("parent")
        return self._parent

    @property
    def guid(self):
        self._tick("guid")
        return "guid-" + self._name

    def get_name(self):
        self._tick("get_name")
        return self._name

    def get_children(self, recursive=False):
        return []


class ExplodingFlag(CountingObj):
    """A property that raises rather than being absent.

    Python 2's hasattr swallowed every exception, so the old
    `hasattr(o, n) and o.n` form read this as False. ide_flag must too.
    """

    @property
    def has_textual_declaration(self):
        self._tick("has_textual_declaration")
        raise RuntimeError("IDE says no")


class TestIdeFlag:
    def test_reads_the_property_once(self, env):
        utils, _, _ = env
        obj = CountingObj(flags={"has_textual_declaration": True})
        assert utils.ide_flag(obj, "has_textual_declaration") is True
        assert obj.reads["has_textual_declaration"] == 1

    def test_missing_property_is_false(self, env):
        utils, _, _ = env
        obj = CountingObj(missing=["has_textual_declaration"])
        assert utils.ide_flag(obj, "has_textual_declaration") is False

    def test_raising_property_is_false_not_an_error(self, env):
        utils, _, _ = env
        assert utils.ide_flag(ExplodingFlag(), "has_textual_declaration") is False

    def test_falsy_property_is_false(self, env):
        utils, _, _ = env
        obj = CountingObj(flags={"has_textual_declaration": False})
        assert utils.ide_flag(obj, "has_textual_declaration") is False


class TestGetParentPouName:
    def _tree(self, guids, parent_type):
        parent = CountingObj("FB_Thing", parent_type)
        child = CountingObj("DoWork", guids["method"], parent=parent)
        return parent, child

    def test_returns_parent_name_for_a_pou(self, env):
        _, managers, guids = env
        parent, child = self._tree(guids, guids["pou"])
        assert managers.get_parent_pou_name(child) == "FB_Thing"

    def test_returns_parent_name_for_an_interface(self, env):
        _, managers, guids = env
        parent, child = self._tree(guids, guids["itf"])
        assert managers.get_parent_pou_name(child) == "FB_Thing"

    def test_returns_none_for_a_folder_parent(self, env):
        _, managers, guids = env
        parent, child = self._tree(guids, guids["folder"])
        assert managers.get_parent_pou_name(child) is None

    def test_returns_none_without_a_parent(self, env):
        _, managers, guids = env
        assert managers.get_parent_pou_name(CountingObj("Lone", guids["pou"])) is None

    def test_fetches_parent_once(self, env):
        """It used to read obj.parent six times to return one name."""
        _, managers, guids = env
        parent, child = self._tree(guids, guids["pou"])
        managers.get_parent_pou_name(child)
        assert child.reads["parent"] == 1

    def test_supplied_parent_avoids_the_fetch(self, env):
        _, managers, guids = env
        parent, child = self._tree(guids, guids["pou"])
        assert managers.get_parent_pou_name(child, parent=parent) == "FB_Thing"
        assert "parent" not in child.reads


class TestBuildPropertiesProbe:
    class BuildProps(object):
        def __init__(self, valid=True, present=True):
            self.probes = 0
            self._valid = valid
            self._present = present
            self.exclude_from_build = True

        def __getattr__(self, item):
            if item.endswith("_is_valid"):
                object.__getattribute__(self, "__dict__")["probes"] = \
                    object.__getattribute__(self, "probes") + 1
                if not object.__getattribute__(self, "_valid"):
                    return False
                return True
            raise AttributeError(item)

    class Obj(object):
        def __init__(self, type_guid, build_props):
            self._type = type_guid
            self.build_properties = build_props

        @property
        def type(self):
            return self._type

        def get_name(self):
            return "Thing"

    def test_reads_the_attribute(self, env):
        utils, _, guids = env
        utils.clear_attr_probe_cache()
        obj = self.Obj(guids["pou"], self.BuildProps())
        assert utils.read_ide_attrs(obj) == {"exclude_from_build": True}

    def test_probes_once_per_type_not_per_object(self, env):
        """The discovery lookups are what cost round trips; the answer depends
        on the object type, so a second object of that type must not re-probe."""
        utils, _, guids = env
        utils.clear_attr_probe_cache()

        first = self.Obj(guids["pou"], self.BuildProps())
        utils.read_ide_attrs(first)
        probes_after_first = first.build_properties.probes
        assert probes_after_first > 0

        second = self.Obj(guids["pou"], self.BuildProps())
        utils.read_ide_attrs(second)
        assert second.build_properties.probes == 0

    def test_invalid_property_is_skipped(self, env):
        utils, _, guids = env
        utils.clear_attr_probe_cache()
        obj = self.Obj(guids["pou"], self.BuildProps(valid=False))
        assert utils.read_ide_attrs(obj) == {}

    def test_unregistered_type_returns_empty(self, env):
        utils, _, guids = env
        utils.clear_attr_probe_cache()
        obj = self.Obj(guids["folder"], self.BuildProps())
        assert utils.read_ide_attrs(obj) == {}

    def test_clear_forces_a_reprobe(self, env):
        utils, _, guids = env
        utils.clear_attr_probe_cache()
        utils.read_ide_attrs(self.Obj(guids["pou"], self.BuildProps()))
        utils.clear_attr_probe_cache()
        again = self.Obj(guids["pou"], self.BuildProps())
        utils.read_ide_attrs(again)
        assert again.build_properties.probes > 0


class TestGraphicalPouDetection:
    """'missing' and 'present but False' mean opposite things here, so this
    one cannot go through ide_flag."""

    def test_textual_implementation_is_not_graphical(self, env):
        _, managers, guids = env
        obj = CountingObj(type_guid=guids["pou"],
                          flags={"has_textual_implementation": True})
        assert managers.is_graphical_pou(obj) is False

    def test_absent_implementation_flag_defaults_to_textual(self, env):
        _, managers, guids = env
        obj = CountingObj(type_guid=guids["pou"],
                          missing=["has_textual_implementation"])
        assert managers.is_graphical_pou(obj) is False

    def test_present_but_false_means_graphical(self, env):
        _, managers, guids = env
        obj = CountingObj(type_guid=guids["pou"],
                          flags={"has_textual_implementation": False})
        assert managers.is_graphical_pou(obj) is True

    def test_reads_the_flag_once(self, env):
        _, managers, guids = env
        obj = CountingObj(type_guid=guids["pou"],
                          flags={"has_textual_implementation": True})
        managers.is_graphical_pou(obj)
        assert obj.reads["has_textual_implementation"] == 1


class TestFindingApplications:
    """Build finds its applications by walking the tree, every time.

    It used to read a project property the last export had written, and that
    flag went stale in the one direction that mattered: the first build after
    a second application appeared still said "one". The walk is affordable
    only if it reads each object's type once, which is what this pins.
    """

    def _project(self, guids, app_names):
        objs = [CountingObj("Device", guids["device"]),
                CountingObj("Folder", guids["folder"])]
        objs.extend(CountingObj(n, guids["application"]) for n in app_names)
        return Project(children=objs), objs

    def _applications(self, project):
        build = entry_build
        return build.applications(project)

    def test_finds_every_application(self, env):
        project, _ = self._project(env[2], ["App1", "App2"])
        found = self._applications(project)
        assert [a.get_name() for a in found] == ["App1", "App2"]

    def test_a_project_with_none_finds_none(self, env):
        project, _ = self._project(env[2], [])
        assert self._applications(project) == []

    def test_reads_type_once_per_object(self, env):
        project, objs = self._project(env[2], ["App1"])
        self._applications(project)
        assert all(o.reads.get("type") == 1 for o in objs)

    def test_an_object_without_a_type_is_not_an_application(self, env):
        class NoType(object):
            def get_name(self):
                return "Odd"

        assert self._applications(Project(children=[NoType()])) == []

    def test_matches_the_application_guid_case_insensitively(self, env):
        upper = CountingObj("App", env[2]["application"].upper())
        assert self._applications(Project(children=[upper])) == [upper]



class TestCompactCache:
    def test_cache_is_written_without_indentation(self, env, tmp_path):
        utils, _, _ = env
        sync_cache.save_sync_cache(str(tmp_path), {"a/b.st": {"ide_hash": "X"}},
                              {"a": "Y"}, {"g": ["t", False, "a/b.st"]})
        raw = (tmp_path / "sync_cache.json").read_text(encoding="utf-8")
        assert "\n" not in raw
        assert ", " not in raw

    def test_round_trips(self, env, tmp_path):
        utils, _, _ = env
        objects = {"a/b.st": {"ide_hash": "X", "disk_mtime": 1, "disk_size": 2}}
        sync_cache.save_sync_cache(str(tmp_path), objects, {"a": "Y"},
                              {"g": ["t", False, "a/b.st"]})
        loaded = sync_cache.load_sync_cache(str(tmp_path))
        assert loaded["objects"] == objects
        assert loaded["folders"] == {"a": "Y"}
