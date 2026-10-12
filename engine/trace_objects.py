# -*- coding: utf-8 -*-
"""Trace objects in the project, by name: finding one, and reaching its settings.

The trace commands name a trace with --name, and a name is not a trace: it
can be a folder, a POU, or two traces in two applications. Each of those is
refused here with what was found, because "no such trace" sends the reader
looking for a typo when what they need is to know what the name is.
"""
from __future__ import print_function

from engine import entry, ide_private
from engine.ide_read import children_of, kind_of, name_of, parent_of
from engine.plc_trip import one_line
from engine.strings import safe_str

TRACE = "trace"

NO_SCRIPT_TRACE = (
    "this IDE's trace plug-in has no %s, the private member cdsint reaches "
    "an existing trace object's settings through (docs/trace-research.md "
    "15.7), so nothing was read or changed" % ide_private.CREATE_SCRIPT_TRACE)


def named(project, name):
    """(the traces called `name`, the other objects called it)."""
    found = project.find(name, True) or []
    traces = [obj for obj in found if kind_of(obj) == TRACE]
    return traces, [obj for obj in found if kind_of(obj) != TRACE]


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
    """'Application/T1': enough of where it is to tell two apart."""
    parent = parent_of(obj)
    if parent is None:
        return name_of(obj)
    return "%s/%s" % (name_of(parent), name_of(obj))


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


def first_task(application):
    """The name of the application's first task, or None."""
    for child in children_of(application):
        if kind_of(child) != "task_config":
            continue
        for task in children_of(child):
            if kind_of(task) == "task":
                return name_of(task)
    return None
