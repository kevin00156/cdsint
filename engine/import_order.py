# -*- coding: utf-8 -*-
"""Which files an import has to take first, and which orphans go with their parent.

A member cannot be created before the POU that owns it, and deleting a POU
takes its members with it.

Moved out of codesys_compare_engine.py unchanged.
"""
from __future__ import print_function

import os
from engine.strings import safe_str
from engine import unhandled
from engine.ide_read import parent_of


def order_st_files_parents_first(items):
    """Order ST import items so a parent POU is created before its nested children.

    A nested child file is named "<Parent>.<Child>.st" (one extra dot in the base
    name) and depends on its parent "<Parent>.st" existing first. Sorting by
    base-name dot-count (stable) yields "<FB>.st" before "<FB>.Method.st" before
    "<FB>.Prop.Get.st", regardless of disk-scan order. Returns a new list.
    """
    def depth(item):
        base = os.path.splitext(item.get("path", "").replace("\\", "/").split("/")[-1])[0]
        return base.count(".")
    return sorted(items, key=depth)


def orphans_their_parent_takes(to_sync):
    """The orphan objects that will be gone before their own turn comes.

    Removing a POU removes its methods, properties and actions with it, so an
    orphan whose ancestor is on the same list has nothing left to remove when
    the loop reaches it: obj.remove() answers "Object reference not set", and
    the run reports a failure for an object that did exactly what was asked.
    The supervisor hit 51 of those in a single import.

    Worked out before any removal happens, while the tree still answers
    questions about parents. Returns the GUIDs to leave alone; they still
    count as deleted, because they will be.
    """
    doomed = {}
    for item in to_sync:
        if not item.get("is_orphan"):
            continue
        obj = item.get("obj")
        if obj is None:
            continue
        try:
            doomed[safe_str(obj.guid)] = obj
        except Exception as exc:
            unhandled.note(item.get("name") or obj, exc)

    covered = set()
    for guid, obj in doomed.items():
        parent = parent_of(obj)
        while parent is not None:
            try:
                parent_guid = safe_str(parent.guid)
            except Exception:
                break
            if parent_guid in doomed:
                covered.add(guid)
                break
            parent = parent_of(parent)
    return covered
