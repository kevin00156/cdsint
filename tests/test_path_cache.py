# -*- coding: utf-8 -*-
"""Regression tests for the memoized ancestor-path helpers.

get_container_prefix() and get_object_path() used to walk from an object all
the way up the tree on every call, and build_expected_path() calls both for
every object on every run. Each step reads .type / .get_name() / .parent off a
live IDE object, so the walks dominated the per-object cost.

They are now memoized per ancestor. The tests below pin the memoized results
to the ORIGINAL walks, reproduced here verbatim as reference implementations:
a faster answer is only useful if it is the same answer.
"""
import sys

import pytest

from engine import codesys_managers


@pytest.fixture(scope="module")
def env():
    managers = codesys_managers
    return managers, sys.modules["engine.codesys_constants"].TYPE_GUIDS


@pytest.fixture(autouse=True)
def clean_caches(env):
    managers, _ = env
    managers.clear_path_caches()
    yield
    managers.clear_path_caches()


class Node(object):
    """Stand-in for a CODESYS script object that counts IDE-side accesses.

    EVERY property a real script object exposes counts -- .type, .parent,
    .guid and get_name() are all round trips into .NET. Leaving any of them
    uncounted would make the read-budget test below pass while the code
    quietly re-fetched it.
    """

    reads = 0

    def __init__(self, name, type_guid, children=None):
        self._name = name
        self._type = type_guid
        self._children = children or []
        self._parent = None
        for child in self._children:
            child._parent = self

    @property
    def type(self):
        Node.reads += 1
        return self._type

    @property
    def parent(self):
        Node.reads += 1
        return self._parent

    @parent.setter
    def parent(self, value):
        self._parent = value

    @property
    def guid(self):
        Node.reads += 1
        return "guid-" + self._name

    def get_name(self):
        Node.reads += 1
        return self._name

    def get_children(self, recursive=False):
        return list(self._children)


# ── reference implementations: the code as it was before memoization ──

def _reference_object_path(obj, guids, stop_at_application=True):
    path_parts = []
    current = obj
    while current is not None:
        try:
            if not hasattr(current, "parent") or current.parent is None:
                break
            parent = current.parent
            if not hasattr(parent, "type") or not hasattr(parent, "get_name"):
                break
            parent_type = str(parent.type)
            if stop_at_application and parent_type == guids["application"]:
                break
            if parent_type in [guids["plc_logic"], guids["device"]]:
                break
            if parent_type in [guids["task_config"], guids["task"]]:
                break
            path_parts.insert(0, parent.get_name())
            current = parent
        except Exception:
            break
    return path_parts


def _reference_container_prefix(obj, guids):
    parts = []
    current = obj
    app_name = None
    device_name = None
    while current is not None:
        try:
            curr_type = str(current.type)
            if curr_type == guids.get("application"):
                app_name = current.get_name()
            elif curr_type == guids.get("device"):
                device_name = current.get_name()
            if not hasattr(current, "parent"):
                break
            current = current.parent
        except Exception:
            break
    if device_name:
        parts.append(device_name)
    if app_name:
        parts.append(app_name)
    return parts


# ── tree shapes ──

def _trees(g):
    """name -> (root, {leaf_label: node}) covering the shapes that matter."""
    trees = {}

    # Device > Plc Logic > Application > Folder > Folder > POU
    pou = Node("Main", g["pou"])
    inner = Node("Inner", g["folder"], [pou])
    outer = Node("POUs", g["folder"], [inner])
    app = Node("Application", g["application"], [outer])
    plc = Node("Plc Logic", g["plc_logic"], [app])
    dev = Node("Device", g["device"], [plc])
    trees["nested_under_app"] = (Node("Project", "proj", [dev]), {"leaf": pou})

    # POU directly under the Application
    pou2 = Node("PLC_PRG", g["pou"])
    app2 = Node("App", g["application"], [pou2])
    dev2 = Node("PLC", g["device"], [app2])
    trees["direct_under_app"] = (Node("Project", "proj", [dev2]), {"leaf": pou2})

    # Project-global object: no device, no application
    gvl = Node("GlobalGVL", g["gvl"])
    folder = Node("Global", g["folder"], [gvl])
    trees["project_global"] = (Node("Project", "proj", [folder]), {"leaf": gvl})

    # Child of a Task, under Task Configuration
    child = Node("TaskChild", g["pou"])
    task = Node("MainTask", g["task"], [child])
    cfg = Node("Task Configuration", g["task_config"], [task])
    app3 = Node("App", g["application"], [cfg])
    dev3 = Node("PLC", g["device"], [app3])
    trees["under_task"] = (Node("Project", "proj", [dev3]), {"leaf": child})

    # Nested devices: the OUTERMOST one must win
    deep = Node("Deep", g["pou"])
    app4 = Node("App", g["application"], [deep])
    innerdev = Node("InnerDevice", g["device"], [app4])
    outerdev = Node("OuterDevice", g["device"], [innerdev])
    trees["nested_devices"] = (Node("Project", "proj", [outerdev]), {"leaf": deep})

    # Method on a POU under a folder
    method = Node("DoWork", g["method"])
    parent_pou = Node("FB_Thing", g["pou"], [method])
    fbfolder = Node("FunctionBlocks", g["folder"], [parent_pou])
    app5 = Node("App", g["application"], [fbfolder])
    dev5 = Node("PLC", g["device"], [app5])
    trees["method_on_pou"] = (Node("Project", "proj", [dev5]), {"leaf": method})

    return trees


class TestMatchesOriginalWalk:
    @pytest.mark.parametrize("shape", [
        "nested_under_app", "direct_under_app", "project_global",
        "under_task", "nested_devices", "method_on_pou",
    ])
    def test_object_path_matches_reference(self, env, shape):
        managers, guids = env
        _, leaves = _trees(guids)[shape]
        leaf = leaves["leaf"]
        assert managers.get_object_path(leaf) == _reference_object_path(leaf, guids)

    @pytest.mark.parametrize("shape", [
        "nested_under_app", "direct_under_app", "project_global",
        "under_task", "nested_devices", "method_on_pou",
    ])
    def test_container_prefix_matches_reference(self, env, shape):
        managers, guids = env
        _, leaves = _trees(guids)[shape]
        leaf = leaves["leaf"]
        assert managers.get_container_prefix(leaf) == _reference_container_prefix(leaf, guids)

    def test_outermost_device_wins(self, env):
        """Precedence is the subtle part: the original walked upwards letting
        each higher ancestor overwrite the last, so the outer device wins."""
        managers, guids = env
        _, leaves = _trees(guids)["nested_devices"]
        assert managers.get_container_prefix(leaves["leaf"])[0] == "OuterDevice"

    def test_task_children_get_no_subfolder(self, env):
        """Tasks are exported inside the Task Configuration XML, so they must
        not contribute a folder level."""
        managers, guids = env
        _, leaves = _trees(guids)["under_task"]
        assert managers.get_object_path(leaves["leaf"]) == []


class TestCachingBehaviour:
    def test_siblings_reuse_the_cached_chain(self, env):
        """The point of the cache: the second object in a folder must not walk
        the tree again."""
        managers, guids = env
        a = Node("A", guids["pou"])
        b = Node("B", guids["pou"])
        folder = Node("POUs", guids["folder"], [a, b])
        app = Node("Application", guids["application"], [folder])
        dev = Node("PLC", guids["device"], [app])
        Node("Project", "proj", [dev])

        Node.reads = 0
        managers.get_object_path(a)
        managers.get_container_prefix(a)
        first = Node.reads

        Node.reads = 0
        managers.get_object_path(b)
        managers.get_container_prefix(b)
        second = Node.reads

        assert second < first
        assert managers.get_object_path(b) == ["POUs"]
        assert managers.get_container_prefix(b) == ["PLC", "Application"]

    def test_repeated_calls_are_stable(self, env):
        managers, guids = env
        _, leaves = _trees(guids)["nested_under_app"]
        leaf = leaves["leaf"]
        first_path = managers.get_object_path(leaf)
        first_prefix = managers.get_container_prefix(leaf)
        for _ in range(3):
            assert managers.get_object_path(leaf) == first_path
            assert managers.get_container_prefix(leaf) == first_prefix

    def test_clear_forces_a_fresh_walk(self, env):
        """A move keeps the object's GUID, so a stale cache would keep
        reporting the old location."""
        managers, guids = env
        pou = Node("Main", guids["pou"])
        old = Node("OldFolder", guids["folder"], [pou])
        new = Node("NewFolder", guids["folder"])
        app = Node("Application", guids["application"], [old, new])
        dev = Node("PLC", guids["device"], [app])
        Node("Project", "proj", [dev])

        assert managers.get_object_path(pou) == ["OldFolder"]

        old._children.remove(pou)
        new._children.append(pou)
        pou.parent = new

        managers.clear_path_caches()
        assert managers.get_object_path(pou) == ["NewFolder"]

    def test_read_budget_per_object(self, env):
        """Path building is the per-object hot path, and its cost is measured
        in IDE round trips, not instructions. This pins the steady-state count
        so a helper that starts re-fetching what its caller already holds --
        the failure mode behind every regression here so far -- shows up as a
        test failure rather than as seconds on a profile.

        Counted with one sibling already processed, since that is the common
        case at scale. Raise the bound only with a reason.
        """
        managers, guids = env
        first = Node("MethodA", guids["method"])
        second = Node("MethodB", guids["method"])
        pou = Node("FB_Thing", guids["pou"], [first, second])
        folder = Node("FunctionBlocks", guids["folder"], [pou])
        app = Node("Application", guids["application"], [folder])
        dev = Node("PLC", guids["device"], [app])
        Node("Project", "proj", [dev])

        managers.build_expected_path(first, guids["method"], False)  # warm

        Node.reads = 0
        path = managers.build_expected_path(second, guids["method"], False)
        assert path == "PLC/Application/FunctionBlocks/FB_Thing.MethodB.st"
        assert Node.reads <= 9, (
            "build_expected_path made %d IDE reads; it should need at most 9 "
            "once a sibling has warmed the ancestor caches" % Node.reads)

    def test_returns_a_fresh_list_each_time(self, env):
        """Callers mutate the result (build_expected_path strips the last
        element), so handing out the cached object would corrupt it."""
        managers, guids = env
        _, leaves = _trees(guids)["nested_under_app"]
        leaf = leaves["leaf"]
        first = managers.get_object_path(leaf)
        first.append("MUTATED")
        assert managers.get_object_path(leaf) == ["POUs", "Inner"]


class TestDebugFlag:
    def test_is_debug_is_what_init_logging_was_told(self, env):
        """is_debug() is consulted per object inside read_ide_attrs.

        It used to fetch a project property and keep a cache of its own in
        front of it, because each uncached read was a get_project_info()
        round trip. The value now arrives from the settings this run read,
        handed to init_logging() once, so there is nothing left to cache.
        """
        utils = sys.modules["engine.codesys_utils"]
        utils.init_logging(None, True)
        assert utils.is_debug() is True
        utils.init_logging(None, False)
        assert utils.is_debug() is False

    def test_anything_truthy_becomes_a_real_boolean(self, env):
        utils = sys.modules["engine.codesys_utils"]
        utils.init_logging(None, 1)
        assert utils.is_debug() is True
        utils.init_logging(None, None)
        assert utils.is_debug() is False

