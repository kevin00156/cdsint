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

from tests.fakes import Node as BaseNode

from engine import import_items


@pytest.fixture(scope="module")
def engine():
    # The four passes live here now; object_create keeps the per-object
    # operations they call.
    return import_items


class RemovableNode(BaseNode):
    """An IDE object that records whether anybody removed it.

    Wired the other way round from the shared fake — a child is handed its
    parent and adds itself — because that is the order the tree is built in
    here, and the removal test needs a parent that already knows its children.
    """

    def __init__(self, name, type_guid, parent=None):
        BaseNode.__init__(self, name, type_guid, parent=parent)
        self.removed = False
        if parent is not None:
            parent._children.append(self)

    def remove(self):
        if self.removed or (self.parent is not None and self.parent.removed):
            # What the IDE says when the object is already gone.
            raise Exception("Object reference not set to an instance of an object.")
        self.removed = True
        for child in self.get_children(recursive=True):
            child.removed = True


class ProjectRoot(RemovableNode):
    """The tree's root. Not tests/fakes.py's Project, which is the object the
    engine asks for children and properties -- this is the node the walk
    starts from, and removal has to reach it the same way as any other."""

    def __init__(self):
        RemovableNode.__init__(self, "Project", "project-guid")


@pytest.fixture
def a_pou_and_its_method(engine, tmp_path):
    """A POU with one method, both of them orphans this import will remove."""
    guids = sys.modules["engine.codesys_constants"].TYPE_GUIDS
    project = ProjectRoot()
    pou = RemovableNode("MC_BasicControl", guids["pou"], project)
    method = RemovableNode("Main", guids["method"], pou)

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
        project, base_dir, to_sync)
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


class TestAMoveThatCannotHappen:
    """A file that moved to a folder the IDE will not make.

    The content is on disk and readable; only its new home is not there. So
    the update goes ahead and the failure gets a name (SPEC D13). Two earlier
    shapes of this were both worse: returning None said nothing at all, and
    raising put the object's content a release behind for a reason that has
    nothing to do with the content.
    """

    def a_move(self):
        return {"name": "Main", "path": "New/Main.st", "disk_path": "New/Main.st",
                "ide_path": "Old/Main.st", "is_moved": True}

    def test_it_is_recorded_and_the_caller_carries_on(self, monkeypatch):
        from engine import import_items, unhandled

        def refuses(folder_path, project):
            raise RuntimeError("cannot create '%s'" % folder_path)

        monkeypatch.setattr(import_items, "ensure_folder_path", refuses)
        unhandled.start()
        try:
            moved = import_items.move_if_needed(self.a_move(), object(), None)
            assert moved is False
            assert unhandled.names() == ["Main"]
        finally:
            unhandled.start()

    def test_a_move_the_ide_refuses_is_recorded_too(self, monkeypatch):
        from engine import import_items, unhandled

        class Immovable(object):
            parent = None

            def move(self, target):
                raise RuntimeError("the IDE will not move it")

        monkeypatch.setattr(import_items, "ensure_folder_path",
                            lambda folder_path, project: object())
        unhandled.start()
        try:
            assert import_items.move_if_needed(self.a_move(), Immovable(),
                                               None) is False
            assert unhandled.names() == ["Main"]
        finally:
            unhandled.start()
