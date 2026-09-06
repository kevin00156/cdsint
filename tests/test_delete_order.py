# -*- coding: utf-8 -*-
"""Deleting a POU takes its methods with it, so they must not be deleted twice.

An import that removes orphans walks the list in whatever order compare
produced it. When a POU and one of its methods are both on that list and the
POU goes first, the method's turn comes to an object that is no longer
there: obj.remove() answers "Object reference not set", and the supervisor
saw 51 of those in one phase 2 run. Nothing was actually wrong -- every one
of those objects had already gone -- but the run reported 51 failures and
was not ok (SPEC D11).
"""
import sys

import pytest

from engine import codesys_compare_engine


@pytest.fixture(scope="module")
def engine():
    return codesys_compare_engine


class Node(object):
    """An IDE object that records whether anybody removed it."""

    def __init__(self, name, type_guid, parent=None):
        self._name = name
        self.type = type_guid
        self.parent = parent
        self.guid = "guid-" + name
        self.removed = False
        self.children = []
        if parent is not None:
            parent.children.append(self)

    def get_name(self):
        return self._name

    def get_children(self, recursive=False):
        if not recursive:
            return list(self.children)
        out = []
        for child in self.children:
            out.append(child)
            out.extend(child.get_children(recursive=True))
        return out

    def remove(self):
        if self.removed or (self.parent is not None and self.parent.removed):
            # What the IDE says when the object is already gone.
            raise Exception("Object reference not set to an instance of an object.")
        self.removed = True
        for child in self.get_children(recursive=True):
            child.removed = True


class Project(Node):
    def __init__(self):
        Node.__init__(self, "Project", "project-guid")


@pytest.fixture
def a_pou_and_its_method(engine, tmp_path):
    """A POU with one method, both of them orphans this import will remove."""
    guids = sys.modules["engine.codesys_constants"].TYPE_GUIDS
    project = Project()
    pou = Node("MC_BasicControl", guids["pou"], project)
    method = Node("Main", guids["method"], pou)

    def orphan(obj, path):
        return {"path": path, "name": obj.get_name(), "type_guid": obj.type,
                "obj": obj, "is_orphan": True}

    # Parent first, which is the order that used to break: compare emits the
    # POU before the member because it walks the tree top down.
    to_sync = [
        orphan(pou, "Function Blocks/MC_BasicControl/MC_BasicControl.st"),
        orphan(method, "Function Blocks/MC_BasicControl/MC_BasicControl.Main.st"),
    ]
    return project, pou, method, to_sync, str(tmp_path)


def run_import(engine, project, to_sync, base_dir):
    updated, created, failed, deleted, moved = engine.perform_import_items(
        project, base_dir, to_sync, {})
    return {"failed": failed, "deleted": deleted}


def test_a_member_of_a_deleted_pou_is_not_removed_a_second_time(
        engine, a_pou_and_its_method):
    project, pou, method, to_sync, base_dir = a_pou_and_its_method

    counts = run_import(engine, project, to_sync, base_dir)

    assert counts["failed"] == 0
    assert pou.removed and method.removed


def test_it_counts_as_deleted_even_though_nobody_called_remove_on_it(
        engine, a_pou_and_its_method):
    # The count is what a person compares against the orphan list they were
    # shown, so "gone because its parent went" still counts as gone.
    project, pou, method, to_sync, base_dir = a_pou_and_its_method

    assert run_import(engine, project, to_sync, base_dir)["deleted"] == 2


def test_an_orphan_with_no_doomed_ancestor_is_still_removed_itself(
        engine, a_pou_and_its_method):
    # The guard is about ancestors on the same list, not about being a
    # member: a method deleted on its own must still be deleted.
    project, pou, method, to_sync, base_dir = a_pou_and_its_method

    counts = run_import(engine, project, [to_sync[1]], base_dir)

    assert counts == {"failed": 0, "deleted": 1}
    assert method.removed and not pou.removed
