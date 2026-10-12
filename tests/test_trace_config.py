# -*- coding: utf-8 -*-
"""A definition, made into a trace object and read back out of one.

plc trace configures a trace it just created; trace apply configures one a
person may have made and filled in the IDE, so whatever the object held
before has to go first. trace job reads an object back as a definition, and
a variable the person switched off is not part of what it records.
"""
from engine import trace_config
from tests import plc_fakes

JOB = {"task": "MainTask", "variables": ["a.x"], "resolution": "ms",
       "every_n_cycles": 2,
       "trigger": {"variable": "a.x", "edge": "falling", "level": 3,
                   "post_samples": 10}}


def trace_object(variables=(), disabled=(), task="MainTask"):
    api = plc_fakes.TraceApi([], u"", None)
    for name in variables:
        api.add_trace_variable(variableName=name)
    api.disabled = set(disabled)
    api.task_name = task
    return api


def configured(api, definition):
    assert trace_config.configure(api, definition,
                                  plc_fakes.Resolution) is None
    return api


def test_configure_replaces_what_the_object_held():
    api = configured(trace_object(variables=["Old.a", "Old.b"]),
                     {"task": "MainTask", "variables": ["PLC_PRG.n"],
                      "resolution": "us", "every_n_cycles": 1})
    assert [v.variable_name for v in api.variable_list] == ["PLC_PRG.n"]


def test_configure_moves_the_trace_to_the_definitions_task():
    api = configured(trace_object(task="FastTask"),
                     dict(JOB, task="MainTask"))
    assert api.task_name == "MainTask"


def test_a_definition_without_a_trigger_switches_an_old_one_off():
    api = configured(trace_object(), JOB)
    configured(api, dict((k, v) for k, v in JOB.items() if k != "trigger"))
    assert api.trigger_enabled is False


def test_a_definition_without_a_condition_clears_an_old_one():
    api = trace_object()
    api.record_condition = "PLC_PRG.b"
    configured(api, {"task": "MainTask", "variables": ["a.x"],
                     "resolution": "us", "every_n_cycles": 1})
    assert not api.record_condition


def test_describe_leaves_out_switched_off_variables():
    definition, left_out = trace_config.describe(
        trace_object(variables=["a.x", "a.y"], disabled=["a.y"]),
        plc_fakes.Resolution)
    assert definition["variables"] == ["a.x"]
    assert left_out == ["a.y"]


def test_a_definition_round_trips():
    api = configured(trace_object(), JOB)
    assert trace_config.describe(api, plc_fakes.Resolution) == (JOB, [])


def test_a_condition_round_trips():
    job = {"task": "MainTask", "variables": ["a.x"], "resolution": "us",
           "every_n_cycles": 1, "record_condition": "PLC_PRG.b"}
    api = configured(trace_object(), job)
    assert trace_config.describe(api, plc_fakes.Resolution)[0] == job


class DotNetNumber(object):
    """What the IDE hands back for a number: not a Python int, so json
    refuses it, though int() and str() both work (seen on the bench)."""

    def __init__(self, value):
        self.value = value

    def __int__(self):
        return self.value

    def __str__(self):
        return str(self.value)


def test_describe_hands_back_plain_python_values():
    import json
    api = configured(trace_object(), JOB)
    api.every_n_cycles = DotNetNumber(2)
    api.post_trigger_samples = DotNetNumber(10)
    definition, _left_out = trace_config.describe(api, plc_fakes.Resolution)
    assert json.loads(json.dumps(definition)) == JOB
