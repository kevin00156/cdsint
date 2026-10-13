# -*- coding: utf-8 -*-
"""in_script_run: online calls from a timer tick, where no script is running.

ScriptOnline.create_online_application raises "Stack empty" unless a script
run is on its executor's stack, and the watcher calls from a timer tick after
its own script has returned. in_script_run asks the executor for a one-line
nested run around the call. The private fields are faked here: _field is the
one place that reaches them, and under CPython it has no .NET to look into.
"""
import sys

import pytest

from engine import codesys_online, ide_private


class Stack(object):
    """System.Collections.Generic.Stack, as far as Count goes."""

    def __init__(self, count):
        self.Count = count


class Executor(object):
    """IScriptExecutor.ExecuteSource: runs the source as a nested script run,
    which is what pushes the run onto ScriptOnline's stack."""

    def __init__(self, stack):
        self.stack = stack
        self.sources = []

    def ExecuteSource(self, source):
        self.sources.append(source)
        self.stack.Count += 1
        try:
            exec(source, {})
        finally:
            self.stack.Count -= 1


@pytest.fixture
def fields(monkeypatch):
    """Point _field at a fake executor and stack; returns both."""
    stack = Stack(0)
    executor = Executor(stack)
    found = {ide_private.EXECUTOR: executor,
             ide_private.EXECUTION_STACK: stack}
    monkeypatch.setattr(ide_private, "_field",
                        lambda obj, name: found.get(name))
    return found


def test_a_tick_runs_the_call_inside_a_nested_run(fields):
    stack = fields[ide_private.EXECUTION_STACK]
    seen = []
    result = ide_private.in_script_run(object(),
                                       lambda: seen.append(stack.Count) or 7)
    assert result == 7
    assert seen == [1]
    assert len(fields[ide_private.EXECUTOR].sources) == 1


def test_inside_a_running_script_the_call_goes_straight_through(fields):
    fields[ide_private.EXECUTION_STACK].Count = 1
    assert ide_private.in_script_run(object(), lambda: "direct") == "direct"
    assert fields[ide_private.EXECUTOR].sources == []


def test_the_calls_own_exception_reaches_the_caller(fields):
    def fails():
        raise ValueError("no gateway")
    with pytest.raises(ValueError, match="no gateway"):
        ide_private.in_script_run(object(), fails)


def test_nothing_is_left_parked_on_sys(fields):
    ide_private.in_script_run(object(), lambda: None)
    assert not hasattr(sys, ide_private._PARKED)


def test_a_missing_private_field_means_calling_as_is(fields):
    del fields[ide_private.EXECUTOR]
    assert ide_private.in_script_run(object(), lambda: "as is") == "as is"


def test_outside_an_ide_there_is_no_field_to_find():
    assert ide_private._field(object(), ide_private.EXECUTOR) is None


def test_the_login_check_asks_through_a_nested_run(fields):
    """The pre-flight's question, with an `online` that only answers inside
    a script run: before in_script_run it got "Stack empty" for every
    application and reported nothing logged in."""
    stack = fields[ide_private.EXECUTION_STACK]

    class Session(object):
        is_logged_in = True

    class Online(object):
        def create_online_application(self, app):
            if not stack.Count:
                raise SystemError("Stack empty.")
            return Session()

    assert codesys_online._is_logged_in(Online(), object()) is True


def test_without_dotnet_there_is_no_script_trace():
    """Outside the IDE: the caller refuses by name rather than guessing."""
    assert ide_private.script_trace(
        object(), 0, "00000000-0000-0000-0000-000000000000") is None


def test_without_dotnet_there_is_no_loader():
    assert ide_private.loader_for(object()) is None


def test_an_editor_without_the_view_field_has_no_loader(monkeypatch):
    monkeypatch.setattr(ide_private, "_field", lambda obj, name: None)
    assert ide_private.loader_for(object()) is None


class Kind(object):
    def __init__(self, name, method=None):
        self.Name = name
        self.method = method

    def GetMethod(self, name, flags):
        return self.method


class Assembly(object):
    """The trace plug-in's assembly, counting how often it is scanned."""

    def __init__(self, kinds):
        self.kinds = kinds
        self.scans = 0

    def GetTypes(self):
        self.scans += 1
        return self.kinds


def test_the_private_creator_is_looked_up_once_per_assembly(monkeypatch):
    """trace list reaches one trace after another; the assembly's types
    are scanned for the member once, not once per trace (#10)."""
    monkeypatch.setattr(ide_private, "_CREATORS", {})
    creator = object()
    assembly = Assembly([Kind("Other"),
                         Kind(ide_private.SCRIPT_TRACE_TYPE, creator)])
    for _ in range(3):
        assert ide_private._creator(assembly, 0) is creator
    assert assembly.scans == 1


def test_an_assembly_without_the_member_has_no_creator(monkeypatch):
    monkeypatch.setattr(ide_private, "_CREATORS", {})
    assert ide_private._creator(Assembly([Kind("Other")]), 0) is None
