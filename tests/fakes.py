# -*- coding: utf-8 -*-
"""One stand-in for each thing the IDE hands the engine.

There were six copies of `Projects`, five of `Info`, five of `DeafUI` and six
of `Node`, and the copies had started to disagree: one `DeafUI` recorded what
it was told and the rest swallowed it, and the two `FakeTimer`s presented two
different interfaces for the same `System.Windows.Forms.Timer` — one taking
`(interval, handler)` in its constructor, one taking `.Interval` and
`.Tick +=`. A fake that disagrees with the other copy of itself is a fake that
disagrees with the IDE, and only one of them can be right.

These are deliberately the *plain* shapes. A test that needs a fake to do
something odd — count reads, refuse to be removed twice, keep a sentinel where
the UI goes — subclasses it there, where the oddity is next to the assertion
that needs it. Adding the oddity here would hand it to every other test as a
behaviour they did not ask for and nobody would think to check.
"""


class Info(object):
    """CODESYS's project info: a `.values` mapping of project properties."""

    def __init__(self, values):
        self.values = values


class Project(object):
    """The open project: its objects, its path, and its properties."""

    def __init__(self, values=None, children=(), path="Fake.project",
                 application=None):
        self.values = values if values is not None else {}
        self._children = list(children)
        self.path = path
        self.active_application = application
        self.saves = 0

    def get_project_info(self):
        return Info(self.values)

    def get_children(self, recursive=False):
        return list(self._children)

    def get_name(self):
        return "FakeProject"

    def save(self):
        self.saves += 1


class Projects(object):
    """CODESYS's `projects`: `primary` is the open one, or None."""

    def __init__(self, primary=None):
        self.primary = primary


class Node(object):
    """One object in the project tree.

    The four things a real script object exposes and the engine reads: a name,
    a type GUID, a parent and a GUID of its own.
    """

    def __init__(self, name, type_guid, children=None, parent=None):
        self._name = name
        self.type = type_guid
        self.guid = "guid-" + name
        self.parent = parent
        self._children = list(children or [])
        for child in self._children:
            child.parent = self

    def get_name(self):
        return self._name

    def get_children(self, recursive=False):
        if not recursive:
            return list(self._children)
        out = []
        for child in self._children:
            out.append(child)
            out.extend(child.get_children(recursive=True))
        return out


class DeafUI(object):
    """Swallows every popup, and remembers it was asked.

    Swallowing is what most tests want: what is left is the return value,
    which is the thing under test (SPEC D11). `said` is here because half the
    copies of this class had it and the other half did not, and a test that
    wants to check a message was shown should not have to write its own fake
    to do it.
    """

    def __init__(self):
        self.said = []

    def __getattr__(self, level):
        def show(*args, **kwargs):
            self.said.append((level, args[0] if args else None))
        return show


class DeafSystem(object):
    """CODESYS's `system`, with a UI that says nothing out loud.

    A fresh `DeafUI` per instance, not one shared on the class: `said` would
    otherwise carry one test's messages into the next.
    """

    def __init__(self):
        self.ui = DeafUI()

    def delay(self, milliseconds):
        pass


class FakeSystem(object):
    """CODESYS's `system`, with a sentinel where the UI should be.

    The string is the point. cds/ide/silent.py swaps `system.ui` for a
    stand-in while a body runs and puts the original back afterwards, and a
    test can only prove the second half happened if the original is something
    no engine code could have produced. A `DeafUI` there would look the same
    before and after.

    Use DeafSystem when the test wants the popups swallowed; use this one when
    the test is about the swapping itself.
    """

    def __init__(self):
        self.ui = "the real ui, which must survive"
        self.abortable = False

    def delay(self, milliseconds):
        pass


class StubManager(object):
    """The object manager, recording what it was asked to create.

    `calls` is (container, name, type_guid) per call — the whole triple, so a
    test that only cares about two of them can ignore one, rather than each
    copy recording a different pair and neither being able to answer the
    other's question. `makes` decides what create() hands back: the IDE
    returns the new object, and returning None is what it does when it will
    not make one.
    """

    def __init__(self, makes=None):
        self.calls = []
        self.makes = makes

    def create(self, container, name, file_path, type_guid):
        self.calls.append((container, name, type_guid))
        return self.makes(name, type_guid) if self.makes else None


class FakeTimer(object):
    """`System.Windows.Forms.Timer`, both of the ways it is used.

    `cds/ide/watcher.py` takes an injected factory and calls it with
    `(interval_ms, handler)`; what comes back is already running, because
    making one is how the watcher arms itself. `engine/codesys_ui.py`'s
    `show_toast` news one up empty and then sets `.Interval`, does
    `.Tick += handler` and calls `Start()`. Same .NET class, two call shapes,
    so one fake answers both — and a change to either side now has one fake to
    disagree with rather than two.
    """

    def __init__(self, interval_ms=None, handler=None):
        self.interval_ms = interval_ms
        self.handler = handler
        self.started = handler is not None
        self.stopped = False
        self.disposed = False
        self.Tick = self

    @property
    def Interval(self):
        return self.interval_ms

    @Interval.setter
    def Interval(self, milliseconds):
        self.interval_ms = milliseconds

    def __iadd__(self, handler):
        """`timer.Tick += handler` on a .NET event."""
        self.handler = handler
        return self

    def Start(self):
        self.started = True

    def Stop(self):
        self.started = False
        self.stopped = True

    def Dispose(self):
        self.disposed = True


def make_globals(path="C:\\p\\softplc.project"):
    """The `globals()` an IDE-side entry point is handed."""
    return {"system": DeafSystem(),
            "projects": Projects(Project(path=path) if path else None)}
