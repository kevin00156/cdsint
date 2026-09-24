# -*- coding: utf-8 -*-
"""A task's period, read out of the task configuration's native XML export.

The fixture is a real export from the bench project: three cyclic tasks, two
spelling their interval as an IEC literal in ms and one as a bare number in
microseconds. Every rule `plc trace` sizes and judges by starts here, so a
misread period is a wrong buffer and a wrong verdict at once.
"""
import io
import os

import pytest

from cds.core import trace_period

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                       "trace_task_config.xml")


def exported():
    with io.open(FIXTURE, encoding="utf-8") as handle:
        return handle.read()


def config(*tasks):
    """A task configuration export holding these (name, kind, time, unit)."""
    entries = u"".join(
        u'<Single Type="{6198ad31}" Method="IArchivable">'
        u'<Single Name="MetaObject"><Single Name="Name">%s</Single></Single>'
        u'<Single Name="Object"><Single Name="Kindoftask">%s</Single>'
        u'<Single Name="Interval"><Single Name="Time">%s</Single>'
        u'<Single Name="Unit">%s</Single></Single></Single></Single>'
        % task for task in tasks)
    return u'<?xml version="1.0" encoding="utf-16"?><ExportFile>%s</ExportFile>' \
        % entries


@pytest.mark.parametrize("task, period", [
    ("MainTask", 4000),          # t#4ms, Unit ms
    ("FoETask", 100000),         # t#100ms, Unit ms
    ("EtherCAT_Task", 1000),     # 1000, Unit µs
])
def test_the_bench_projects_tasks(task, period):
    assert trace_period.task_period_us(exported(), task) == (period, None)


def test_bytes_with_a_bom_read_the_same():
    raw = u"﻿".encode("utf-8") + exported().encode("utf-8")
    assert trace_period.task_period_us(raw, "MainTask") == (4000, None)


def test_a_missing_task_lists_the_tasks_there_are():
    period, problem = trace_period.task_period_us(exported(), "FastTask")
    assert period is None
    assert "no task named FastTask" in problem
    assert "EtherCAT_Task, FoETask, MainTask" in problem


def test_the_task_configuration_itself_is_not_a_task():
    _, problem = trace_period.task_period_us(exported(), "Task configuration")
    assert "no task named" in problem


def test_a_task_that_is_not_cyclic_is_refused_with_its_kind():
    xml = config((u"Ev", u"Event", u"", u"ms"))
    period, problem = trace_period.task_period_us(xml, "Ev")
    assert period is None
    assert "task Ev is Event, not Cyclic" in problem
    assert "period" in problem


def test_an_unreadable_interval_is_refused_with_what_was_there():
    xml = config((u"T", u"Cyclic", u"t#fast", u"ms"))
    period, problem = trace_period.task_period_us(xml, "T")
    assert period is None
    assert "task T has an interval cdsint cannot read" in problem
    assert "t#fast" in problem


def test_a_task_with_no_interval_element_is_unreadable_not_a_crash():
    xml = (u'<ExportFile><Single><Single Name="MetaObject">'
           u'<Single Name="Name">T</Single></Single><Single Name="Object">'
           u'<Single Name="Kindoftask">Cyclic</Single></Single></Single>'
           u'</ExportFile>')
    _, problem = trace_period.task_period_us(xml, "T")
    assert "cannot read" in problem


@pytest.mark.parametrize("time, unit, period", [
    (u"t#4ms", u"ms", 4000),
    (u"T#100ms", u"ms", 100000),
    (u"t#500us", u"ms", 500),
    (u"T#500US", u"ms", 500),
    (u"t#1s", u"ms", 1000000),
    (u"t#2.5ms", u"ms", 2500),
    (u"TIME#1s500ms", u"ms", 1500000),
    (u"t#1_000us", u"ms", 1000),
    (u"t#250µs", u"ms", 250),
    (u"1000", u"µs", 1000),
    (u"1000", u"μs", 1000),
    (u"1000", u"us", 1000),
    (u"4", u"ms", 4000),
    (u" 2.5 ", u"ms", 2500),
    (u"1", u"s", 1000000),
    (u"0.25", u"s", 250000),
])
def test_interval_spellings(time, unit, period):
    assert trace_period.interval_us(time, unit) == period


@pytest.mark.parametrize("time, unit", [
    (u"t#0ms", u"ms"),         # not a period
    (u"0", u"us"),
    (u"t#0.5us", u"ms"),       # not a whole microsecond
    (u"1.5", u"us"),
    (u"4", u"min"),            # a unit nobody wrote down
    (u"4", u""),
    (u"", u"ms"),
    (u"nan", u"ms"),
    (u"t#4", u"ms"),           # a literal needs its own unit
    (u"t#4msx", u"ms"),
    (u"-4", u"ms"),
])
def test_intervals_that_are_not_a_period(time, unit):
    assert trace_period.interval_us(time, unit) is None


def test_several_tasks_are_told_apart_by_name_not_position():
    xml = config((u"A", u"Cyclic", u"t#2ms", u"ms"),
                 (u"B", u"Cyclic", u"t#8ms", u"ms"))
    assert trace_period.task_period_us(xml, "B") == (8000, None)
    assert trace_period.task_period_us(xml, "A") == (2000, None)
