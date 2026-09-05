# -*- coding: utf-8 -*-
"""Regression tests for creating POU/interface MEMBERS (method, itf_method,
action, property) from disk.

Two bugs made every member import land in the wrong place, and both are
silent - the object is created, just not where it belongs:

1. POUManager.create() dispatched on the exact 'method' GUID, so 'itf_method'
   (a method on an INTERFACE - a different GUID) matched nothing and fell
   through to the create_pou() fallback.
2. create_new_object() accepted the resolved container as the parent POU on a
   NAME match alone. The export lays members out under a folder named after
   their POU ("Function Blocks/MC_BasicControl/MC_BasicControl.Main.st"), so
   the folder always won and every method became a standalone PROGRAM beside
   the real FB. The next compare saw those strays as orphans and deleted them,
   so each import recreated and destroyed the same objects in a loop.

Both now resolve the real POU/interface, and refuse to create anything when
they cannot.
"""
import io
import os

import pytest


@pytest.fixture(scope="module")
def env(load_engine):
    import sys
    for dep in ("codesys_constants", "codesys_utils", "codesys_managers"):
        load_engine(dep)
    engine = load_engine("codesys_compare_engine")
    return {
        "constants": sys.modules["engine.codesys_constants"],
        "managers": sys.modules["engine.codesys_managers"],
        "engine": engine,
    }


def _write(tmp_path, name, text):
    p = os.path.join(str(tmp_path), name)
    with io.open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


class FakeObj(object):
    """Minimal stand-in for a ScriptObject."""

    def __init__(self, name, type_guid, children=None):
        self._name = name
        self.type = type_guid
        self._children = list(children or [])

    def get_name(self):
        return self._name

    def get_children(self, recursive=False):
        return list(self._children)


class RecordingContainer(FakeObj):
    """A container that records which creator API was called."""

    def __init__(self, name, type_guid, apis, children=None):
        FakeObj.__init__(self, name, type_guid, children)
        self.apis = apis          # names of creators this container exposes
        self.calls = []

    def __getattr__(self, item):
        if item.startswith("create_") and item in self.__dict__.get("apis", []):
            raise AttributeError(item)
        raise AttributeError(item)


def _make_container(name, type_guid, apis, children=None):
    """Build a container exposing exactly `apis` as creator methods."""
    holder = {"calls": []}

    class _C(FakeObj):
        pass

    obj = _C(name, type_guid, children)

    def _make(api):
        def _creator(child_name, *rest):
            holder["calls"].append((api, child_name))
            return FakeObj(child_name, "created")
        return _creator

    for api in apis:
        setattr(obj, api, _make(api))
    obj.calls = holder["calls"]
    return obj


class TestMemberDispatch:
    """POUManager routes members to the container's typed creator, by KIND."""

    @pytest.mark.parametrize("kind,decl,creator", [
        ("method", "METHOD DoIt : BOOL", "create_method"),
        ("itf_method", "METHOD DoIt : BOOL", "create_method"),
        ("action", "x := x + 1;", "create_action"),
        ("property", "PROPERTY Speed : LREAL", "create_property"),
    ])
    def test_member_uses_typed_creator(self, env, tmp_path, kind, decl, creator):
        mgr = env["managers"].POUManager()
        guid = env["constants"].TYPE_GUIDS[kind]
        container = _make_container(
            "IAxisControl", env["constants"].TYPE_GUIDS["itf"],
            [creator, "create_pou", "create_child"])

        path = _write(tmp_path, "%s_%s.st" % (kind, "DoIt"), decl + "\n")
        obj = mgr.create(container, "DoIt", path, guid)

        assert obj is not None
        assert container.calls == [(creator, "DoIt")]

    def test_itf_method_never_becomes_a_pou(self, env, tmp_path):
        """The exact k1.1.0 symptom: IStateMachine.Stop and friends silently
        failed because itf_method matched no branch."""
        mgr = env["managers"].POUManager()
        container = _make_container(
            "IStateMachine", env["constants"].TYPE_GUIDS["itf"],
            ["create_method", "create_pou", "create_child"])

        path = _write(tmp_path, "Stop.st",
                      "//% cds-text-sync.kind=itf_method\n\nMETHOD Stop : BOOL\n")
        mgr.create(container, "Stop", path,
                   env["constants"].TYPE_GUIDS["itf_method"])

        assert [api for api, _ in container.calls] == ["create_method"]

    def test_member_on_wrong_container_fails_loud(self, env, tmp_path):
        """A folder exposes create_pou but no create_method. Creating a stray
        PROGRAM there is worse than failing: the next compare deletes it."""
        mgr = env["managers"].POUManager()
        folder = _make_container(
            "MC_BasicControl", env["constants"].TYPE_GUIDS["folder"],
            ["create_pou", "create_child"])

        path = _write(tmp_path, "Main.st", "METHOD Main : BOOL\n")
        obj = mgr.create(folder, "Main", path,
                         env["constants"].TYPE_GUIDS["method"])

        assert obj is None
        assert folder.calls == [], "must not fall back to create_pou/create_child"


class TestParentResolution:
    """create_new_object must resolve the parent POU, not a same-named folder."""

    class _StubManager(object):
        def __init__(self):
            self.calls = []

        def create(self, container, name, file_path, type_guid):
            self.calls.append((container, name, type_guid))
            return FakeObj(name, type_guid)

    def _managers(self):
        stub = self._StubManager()
        return stub, {"default": stub, "native": stub}

    def test_prefers_pou_over_same_named_folder(self, env, tmp_path):
        """Folder 'MC_BasicControl' contains FB 'MC_BasicControl'. The member
        belongs on the FB."""
        constants = env["constants"]
        fb = FakeObj("MC_BasicControl", constants.TYPE_GUIDS["pou"])
        folder = FakeObj("MC_BasicControl", constants.TYPE_GUIDS["folder"], [fb])
        project = FakeObj("Project", "project", [folder])

        stub, managers = self._managers()
        path = _write(tmp_path, "MC_BasicControl.Main.st", "METHOD Main : BOOL\n")
        env["engine"].create_new_object(
            "MC_BasicControl/MC_BasicControl.Main.st", path, managers, {}, {},
            project)

        assert stub.calls, "manager.create was never called"
        container, name, type_guid = stub.calls[0]
        assert container is fb, "member was attached to the folder, not the FB"
        assert name == "Main"
        assert type_guid == constants.TYPE_GUIDS["method"]

    def test_container_that_is_the_pou_still_works(self, env, tmp_path):
        """Stripped layout: the resolved container IS the parent FB."""
        constants = env["constants"]
        fb = FakeObj("MC_BasicControl", constants.TYPE_GUIDS["pou"])
        project = FakeObj("Project", "project", [fb])

        stub, managers = self._managers()
        path = _write(tmp_path, "m.st", "METHOD Main : BOOL\n")
        env["engine"].create_new_object(
            "MC_BasicControl/MC_BasicControl.Main.st", path, managers, {}, {},
            project)

        assert stub.calls[0][0] is fb

    def test_interface_parent_is_resolved(self, env, tmp_path):
        constants = env["constants"]
        itf = FakeObj("IStateMachine", constants.TYPE_GUIDS["itf"])
        folder = FakeObj("StateMachine", constants.TYPE_GUIDS["folder"], [itf])
        project = FakeObj("Project", "project", [folder])

        stub, managers = self._managers()
        path = _write(tmp_path, "s.st",
                      "//% cds-text-sync.kind=itf_method\n\nMETHOD Stop : BOOL\n")
        env["engine"].create_new_object(
            "StateMachine/IStateMachine.Stop.st", path, managers, {}, {}, project)

        container, name, type_guid = stub.calls[0]
        assert container is itf
        assert name == "Stop"
        assert type_guid == constants.TYPE_GUIDS["itf_method"]

    def test_no_pou_parent_creates_nothing(self, env, tmp_path):
        """Only a same-named folder exists — no FB inside it. Skip rather than
        drop a stray PROGRAM into the folder."""
        constants = env["constants"]
        folder = FakeObj("MC_BasicControl", constants.TYPE_GUIDS["folder"])
        project = FakeObj("Project", "project", [folder])

        stub, managers = self._managers()
        path = _write(tmp_path, "MC_BasicControl.Main.st", "METHOD Main : BOOL\n")
        res = env["engine"].create_new_object(
            "MC_BasicControl/MC_BasicControl.Main.st", path, managers, {}, {},
            project)

        assert res is None
        assert stub.calls == []

    def test_name_map_folder_is_ignored(self, env, tmp_path):
        """A folder cached in name_map must not be taken as the parent POU."""
        constants = env["constants"]
        fb = FakeObj("MC_BasicControl", constants.TYPE_GUIDS["pou"])
        folder = FakeObj("MC_BasicControl", constants.TYPE_GUIDS["folder"], [fb])
        project = FakeObj("Project", "project", [folder])
        name_map = {"MC_BasicControl": [folder]}

        stub, managers = self._managers()
        path = _write(tmp_path, "MC_BasicControl.Main.st", "METHOD Main : BOOL\n")
        env["engine"].create_new_object(
            "MC_BasicControl/MC_BasicControl.Main.st", path, managers, name_map,
            {}, project)

        assert stub.calls[0][0] is fb
