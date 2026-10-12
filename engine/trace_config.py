# -*- coding: utf-8 -*-
"""A trace definition, written into a trace object and read back out of one.

The definition is cds/core/trace_job.py DEFINITION_KEYS: what to record, in
which task, how finely, and what starts or filters it. plc trace writes one
into the trace it creates for a run; trace apply into one a person may have
made in the IDE; trace job reads one back. One place for both directions,
so what apply writes is what job reads and what plc trace records.

Also the task's period, which plc trace and trace save both judge
completeness against.
"""
from __future__ import print_function

from cds.core import trace_period
from engine import object_kind
from engine.ide_read import children_of, kind_of, name_of
from engine.plc_trip import one_line
from engine.strings import safe_str

# The job's resolution word -> the member of the IDE's Resolution enum.
RESOLUTIONS = {"us": "MicroSeconds", "ms": "MilliSeconds"}

# The job's edge word -> the member of the trace plug-in's edge enum, the
# names research 13.4 set.
EDGES = {"rising": "Positive", "falling": "Negative", "both": "Both"}


def configure(api, definition, resolution_enum):
    """Make `api` record `definition`. None, or why it could not.

    Whatever the object held first goes: trace apply may be pointed at a
    trace a person filled in, and variables, a trigger or a condition left
    over from that would be recorded beside what the definition asks for.
    """
    try:
        api.variable_list.clear()
        if api.task_name != definition["task"]:
            api.task_name = definition["task"]
        for name in definition["variables"]:
            api.add_trace_variable(variableName=name)
        api.resolution = getattr(resolution_enum,
                                 RESOLUTIONS[definition["resolution"]])
        api.every_n_cycles = definition["every_n_cycles"]
        _trigger(api, definition.get("trigger"))
        _condition(api, definition.get("record_condition"))
    except Exception as exc:
        return one_line(exc)
    return None


def _trigger(api, trigger):
    """Every trigger setting, enabled last; or an old trigger switched off.

    A trigger left half set makes the next start() fail without saying why
    (research 4), so all of them go in before it is switched on. The edge
    enum is the plug-in's own and not a script global, so its type is read
    off the value the trace already holds. The level goes in as text, which
    the IDE converts to the variable's type (research 4). Only an enabled
    trigger is switched off, so a new trace sees no setting it did not ask
    for.
    """
    if trigger is None:
        if api.trigger_enabled:
            api.trigger_enabled = False
        return
    api.trigger_variable = trigger["variable"]
    api.trigger_edge = getattr(type(api.trigger_edge), EDGES[trigger["edge"]])
    api.trigger_level = str(trigger["level"])
    api.post_trigger_samples = trigger["post_samples"]
    api.trigger_enabled = True


def _condition(api, condition):
    if condition is not None:
        api.record_condition = condition
    elif api.record_condition:
        api.record_condition = ""


def describe(api, resolution_enum):
    """(the definition `api` records, the variables it has switched off).

    Every value comes back as a plain Python one: the IDE hands out .NET
    numbers and strings, and json, which the result travels in, refuses a
    .NET UInt32 (seen on the bench). Enums are matched against their
    members rather than by name: the IDE's str() of one is not something
    the job has a word for.
    """
    variables, left_out = [], []
    for variable in api.variable_list:
        (variables if variable.enabled else left_out).append(
            safe_str(variable.variable_name))
    definition = {"task": safe_str(api.task_name), "variables": variables,
                  "resolution": _word(RESOLUTIONS, resolution_enum,
                                      api.resolution),
                  "every_n_cycles": int(api.every_n_cycles)}
    if api.trigger_enabled:
        definition["trigger"] = {
            "variable": safe_str(api.trigger_variable),
            "edge": _word(EDGES, type(api.trigger_edge), api.trigger_edge),
            "level": _number(api.trigger_level),
            "post_samples": int(api.post_trigger_samples)}
    if api.record_condition:
        definition["record_condition"] = safe_str(api.record_condition)
    return definition, left_out


def _word(words, enum, value):
    """The job's word for `value`, a member of `enum`; None if it has none."""
    for word, member in words.items():
        if getattr(enum, member, None) == value:
            return word
    return None


def _number(text):
    """A trigger level as the job writes it: a number, whole when it is."""
    number = float(str(text))
    return int(number) if number == int(number) else number


def task_period_us(project, application, task):
    """(the period of `task` in microseconds, None), or (None, why not)."""
    config = task_configuration(application)
    if config is None:
        return None, ("application %s has no task configuration, so there "
                      "is no task to sample in" % name_of(application))
    try:
        xml = object_kind.native_xml_of(project, config, recursive=True)
    except Exception as exc:
        return None, ("the task configuration could not be exported to read "
                      "the task's period: " + one_line(exc))
    if not xml:
        return None, "exporting the task configuration wrote nothing to read"
    return trace_period.task_period_us(xml, task)


def task_configuration(application):
    """The application's task configuration object, or None."""
    for child in children_of(application):
        if kind_of(child) == "task_config":
            return child
    return None
