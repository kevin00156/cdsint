# -*- coding: utf-8 -*-
"""Trace objects in the project, by name: finding one, and reaching its settings.

The trace commands name a trace with --name, and a name is not a trace: it
can be a folder, a POU, or two traces in two applications. Each of those is
refused here with what was found, because "no such trace" sends the reader
looking for a typo when what they need is to know what the name is.
"""
from __future__ import print_function

from engine import entry, ide_private, unhandled
from engine.ide_read import guid_of, kind_of, name_of, parent_of
from engine.plc_trip import one_line
from engine.strings import safe_str

TRACE = "trace"
FOLDER = "folder"
APPLICATION = "application"
# What failed_objects names when the project will not list its objects.
PROJECT_TREE = "the project's object tree"

NO_SCRIPT_TRACE = (
    "this IDE's trace plug-in has no %s, the private member cdsint reaches "
    "an existing trace object's settings through (docs/trace-research.md "
    "15.7), so nothing was read or changed" % ide_private.CREATE_SCRIPT_TRACE)


def named(project, name, kind=TRACE):
    """(the objects of `kind` called `name`, the other objects called it).

    The IDE's own find, which reaches into folders (docs/trace-research.md
    15.12) and matches names the way the IDE does.
    """
    found = [(obj, kind_of(obj)) for obj in project.find(name, True) or []]
    return ([obj for obj, its in found if its == kind],
            [obj for obj, its in found if its != kind])


def find(project, name):
    """(the one trace called `name`, None), or (None, why there is not one)."""
    traces, others = named(project, name)
    if len(traces) == 1:
        return traces[0], None
    if traces:
        return None, several(name, traces)
    return None, "no trace object named %s%s" % (name, what_else(others))


def several(name, traces):
    return ("%d trace objects are named %s (%s), and --name cannot say "
            "which; rename one" % (len(traces), name,
                                   ", ".join(path_of(t) for t in traces)))


def what_else(others):
    """'; it is a folder' -- what a name that is not a trace names instead."""
    if not others:
        return ""
    return "; the name belongs to %s" % ", ".join(
        "%s (a %s)" % (path_of(obj), kind_of(obj) or "kind cdsint does not "
                                                     "know")
        for obj in others)


def path_of(obj):
    """'Device/Plc Logic/Application/Traces/T1': where it is, from the top
    of the tree. The parent alone told nothing apart when two traces of one
    name sat in two applications, which both name their parent the same."""
    names = []
    while obj is not None and not _the_project(obj):
        names.append(name_of(obj))
        obj = parent_of(obj)
    return "/".join(reversed(names))


def _the_project(obj):
    """The project itself, where every chain of parents ends in the IDE.

    It has no name of its own, and name_of would print its description
    (docs/trace-research.md 15.12). Both tests are needed: an object whose
    plug-in is missing has no name either, but it has a parent.
    """
    if parent_of(obj) is not None:
        return False
    try:
        obj.get_name()
    except Exception:
        return True
    return False


def scripted(ide_globals, project, obj):
    """(the trace object's settings, None), or (None, why not)."""
    api = ide_private.script_trace(entry.borrowed(ide_globals, "trace"),
                                   project.handle, safe_str(obj.guid))
    if api is None:
        return None, NO_SCRIPT_TRACE
    return api, None


def reach(ide_globals, project, name):
    """(the settings of the one trace called `name`, None), or (None, why)."""
    obj, problem = find(project, name)
    if problem:
        return None, problem
    return scripted(ide_globals, project, obj)


def every(project):
    """Every trace object in the project, wherever it sits in the tree.

    One recursive enumeration, the one export and discover make, so this
    sees what they see (docs/trace-research.md 15.13). Each object's kind is
    read once; one that will not say is named in engine/unhandled.py.
    """
    try:
        found = project.get_children(True)
    except Exception as exc:
        unhandled.note(PROJECT_TREE, exc)
        return []
    return [obj for obj in found if kind_of(obj) == TRACE]


def folder_named(project, name):
    """(the one folder called `name` in the active application, None), or
    (None, why there is not one).

    Never made here: a folder is the person's to lay out, and a typo would
    otherwise become a folder. One in another application is refused: a
    trace moved there belongs to that application, which does not have the
    task it was made with (kevin00156/cdsint#5).
    """
    if not name.strip():
        return None, "--folder is empty; it takes a folder's name"
    if "/" in name:
        return None, ("--folder takes a folder's name, not a path like %s; "
                      "the name is the path's last part" % name)
    application = project.active_application
    folders, others = named(project, name, FOLDER)
    mine = [obj for obj in folders if owned_by(obj, application)]
    if len(mine) == 1:
        return mine[0], None
    if mine:
        return None, ("%d folders are named %s (%s), and --folder cannot say "
                      "which; rename one" % (len(mine), name, ", ".join(
                          path_of(obj) for obj in mine)))
    if folders:
        return None, ("the folder %s is not in %s, the application the trace "
                      "is made in (%s)" % (name, name_of(application),
                                           ", ".join(path_of(obj)
                                                     for obj in folders)))
    if others:
        return None, "%s is not a folder%s" % (name, what_else(others))
    return None, ("no folder named %s in %s; make it in the IDE first"
                  % (name, name_of(application)))


def owned_by(obj, application):
    """Whether `application` is the nearest application above `obj`.

    The project at the top has no kind to read (docs/trace-research.md
    15.12), so the walk stops below it rather than asking.
    """
    wanted = guid_of(application)
    obj = parent_of(obj)
    while obj is not None:
        if guid_of(obj) == wanted:
            return True
        parent = parent_of(obj)
        if parent is None or kind_of(obj) == APPLICATION:
            return False
        obj = parent
    return False


def move(obj, folder):
    """None once `obj` sits in `folder`, or why it does not.

    trace.create takes only an application: handed a folder it makes
    nothing (docs/trace-research.md 15.12), so a trace is made there and
    moved. The settings create handed back still configure it afterwards:
    move keeps the object's GUID, which is all they hold (15.13).
    """
    try:
        obj.move(folder)
    except Exception as exc:
        return ("%s was made at %s, with nothing to record yet, but could not "
                "be moved into %s: %s" % (name_of(obj), path_of(obj),
                                         path_of(folder), one_line(exc)))
    return None


def create(ide_globals, application, name, task):
    """(a new trace object's settings, None), or (None, why there is none).

    While the application is logged in, CODESYS adds no object to it, and
    trace.create says so only by handing back a NoScriptTraceObject, whose
    one member is is_trace_object = False (docs/trace-research.md 15).
    Without this check that surfaced as "no attribute 'variable_list'".
    """
    try:
        api = entry.borrowed(ide_globals, "trace").create(application, name,
                                                          task)
    except Exception as exc:
        return None, "%s could not be created: %s" % (name, one_line(exc))
    if getattr(api, "is_trace_object", True) is False:
        return None, ("%s could not be created: the project is logged in to "
                      "the controller, and CODESYS adds no object to an "
                      "application that is online. Log out and run this "
                      "again; a trace that already exists can be changed "
                      "while logged in" % name)
    return api, None
