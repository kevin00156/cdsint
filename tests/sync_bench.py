# -*- coding: utf-8 -*-
"""A project tree the engine can export, compare and import end to end.

tests/fakes.py holds the plain shapes. This is the one test benches kept
writing for themselves: a tree of POUs and folders whose text can be edited,
which can be moved and removed the way the IDE does it, and a sync folder the
three commands run against. The bugs it exists for are the ones that only
show up across commands -- an import followed by an export, a compare
followed by a compare -- so every run goes through the real entry bodies.
"""
import os
import sys
import time
import types

from cds.core import settings
from engine import change_detect, entry_export, entry_import
from engine.codesys_constants import TYPE_GUIDS
from tests.fakes import DeafSystem, Node, Project, Projects


class Text(object):
    def __init__(self, text):
        self.text = text


class Item(Node):
    """One IDE object. `owner` is the list it sits in, so a top-level object
    (whose parent is None, as in the IDE's script API) can be removed too."""

    def __init__(self, name, kind, children=None, decl=None, impl=None):
        Node.__init__(self, name, TYPE_GUIDS[kind], children)
        self.has_textual_declaration = decl is not None
        self.has_textual_implementation = impl is not None
        if decl is not None:
            self.textual_declaration = Text(decl)
        if impl is not None:
            self.textual_implementation = Text(impl)
        self.owner = None
        for child in self._children:
            child.owner = self._children
        self.removed = False

    def move(self, target):
        self.owner.remove(self)
        target._children.append(self)
        self.owner = target._children
        self.parent = target

    def remove(self):
        self.owner.remove(self)
        self.removed = True


def pou(name, body=u"x := 1;"):
    return Item(name, "pou", impl=body,
                decl=u"FUNCTION_BLOCK %s\nVAR\nEND_VAR" % name)


def folder(name, *children):
    return Item(name, "folder", list(children))


class Tree(Project):
    """The open project, answering for the whole tree when asked to."""

    def __init__(self, top, path):
        Project.__init__(self, {}, top, path)
        for item in self._children:
            item.owner = self._children

    def get_children(self, recursive=False):
        if not recursive:
            return list(self._children)
        out = []
        for child in self._children:
            out.append(child)
            out.extend(child.get_children(recursive=True))
        return out

    def create_folder(self, name):
        made = folder(name)
        made.owner = self._children
        self._children.append(made)
        return made


class Bench(object):
    """The tree, its sync folder, and the three commands over them.

    `answer` is what every Yes/No dialog gets.
    """

    def __init__(self, monkeypatch, tmp_path, *top):
        self.sync = tmp_path / "sync"
        self.sync.mkdir()
        self.tree = Tree(top, str(tmp_path / "Fake.project"))
        self.projects = Projects(self.tree)
        self.answer = True
        for module in (entry_export, entry_import):
            monkeypatch.setattr(module, "projects", self.projects,
                                raising=False)
            monkeypatch.setattr(module, "system", DeafSystem(), raising=False)
        ui = types.ModuleType("engine.codesys_ui")
        ui.ask_yes_no = lambda title, message: self.answer
        monkeypatch.setitem(sys.modules, "engine.codesys_ui", ui)

    def export(self, **written):
        return entry_export.export_project(str(self.sync),
                                           settings.resolve(written),
                                           self.projects)

    def import_(self, **written):
        written.setdefault("safety_backup", False)
        return entry_import.import_project(str(self.sync),
                                           settings.resolve(written),
                                           self.projects)

    def compare(self):
        return change_detect.find_all_changes(str(self.sync), self.projects)

    def path(self, rel):
        return str(self.sync / rel)

    def read(self, rel):
        with open(self.path(rel), "rb") as handle:
            return handle.read().decode("utf-8")

    def write(self, rel, text):
        """Write the file as an editor would, a moment after the last sync:
        the signature a sync recorded has to move, and on a fast machine the
        clock alone may not have."""
        full = self.path(rel)
        if not os.path.isdir(os.path.dirname(full)):
            os.makedirs(os.path.dirname(full))
        later = time.time()
        if os.path.exists(full):
            later = max(later, os.path.getmtime(full))
        with open(full, "wb") as handle:
            handle.write(text.encode("utf-8"))
        os.utime(full, (later + 10, later + 10))

    def edit(self, rel, old, new):
        self.write(rel, self.read(rel).replace(old, new))

    def files(self):
        found = []
        for root, _dirs, names in os.walk(str(self.sync)):
            for name in names:
                if name.endswith(".st"):
                    rel = os.path.relpath(os.path.join(root, name), str(self.sync))
                    found.append(rel.replace(os.sep, "/"))
        return sorted(found)
