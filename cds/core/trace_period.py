# -*- coding: utf-8 -*-
"""A task's cycle period, read from the task configuration's native XML.

Completeness is measured against the sampling period (SPEC 6.8), and the
buffers are sized from it, so `plc trace` needs the period of the task the
job names. The script API has no typed accessor for it; the engine exports
the task configuration object and hands the text here, where it is plain
Python on a string and can be tested without an IDE.

Elements are found by their Name attribute, never by position: the export
is a serialisation of an object graph, and the order of its members is the
serialiser's business, not a contract.
"""
from __future__ import print_function

import re
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation

CYCLIC = "Cyclic"

# U+00B5 MICRO SIGN is what the IDE writes; U+03BC GREEK SMALL LETTER MU is
# what a keyboard often produces, and both mean the same unit.
UNIT_US = {
    "s": 1000000,
    "ms": 1000,
    "us": 1,
    u"µs": 1,
    u"μs": 1,
}

# An IEC time literal: the prefix, then one or more number-unit parts, as in
# t#4ms, T#2.5ms or t#1s500ms. Underscores are IEC digit separators.
LITERAL = re.compile(u"^(?:t|time)#((?:[0-9_.]+(?:ms|us|µs|μs|s))+)$",
                     re.IGNORECASE | re.UNICODE)
PART = re.compile(u"([0-9_.]+)(ms|us|µs|μs|s)",
                  re.IGNORECASE | re.UNICODE)

DECLARATION = re.compile(u"^\\s*<\\?xml[^>]*\\?>", re.UNICODE)


def task_period_us(xml_text, task_name):
    """(the task's period in whole microseconds, None), or (None, problem)."""
    tasks = _tasks(xml_text)
    if task_name not in tasks:
        return None, ("there is no task named %s; the tasks are %s"
                      % (task_name, ", ".join(sorted(tasks)) or "none"))
    kind, time_text, unit = tasks[task_name]
    if kind != CYCLIC:
        return None, ("task %s is %s, not %s; completeness is measured "
                      "against a cyclic task's period" % (task_name, kind,
                                                          CYCLIC))
    period = interval_us(time_text, unit)
    if period is None:
        return None, ("task %s has an interval cdsint cannot read: Time %r, "
                      "Unit %r" % (task_name, time_text, unit))
    return period, None


def interval_us(time_text, unit):
    """The interval in whole microseconds, or None when it cannot be one.

    A literal carries its own unit and wins over `unit`; a bare number is in
    `unit`. Zero and fractions of a microsecond are None: neither is a period
    a sample count can be measured against.
    """
    text = (time_text or u"").strip()
    literal = LITERAL.match(text)
    if literal:
        parts = PART.findall(literal.group(1))
    else:
        parts = [(text, (unit or u"").strip())]
    total = Decimal(0)
    for number, part_unit in parts:
        scale = UNIT_US.get(part_unit.lower())
        value = _decimal(number)
        if scale is None or value is None:
            return None
        total += value * scale
    if total <= 0 or total != total.to_integral_value():
        return None
    return int(total)


def _decimal(text):
    try:
        value = Decimal(text.replace(u"_", u""))
    except InvalidOperation:
        return None
    # Decimal reads "nan" and "inf" too, and neither is an interval.
    return value if value.is_finite() else None


def _tasks(xml_text):
    """{task name: (kind, interval Time text, interval Unit text)}.

    A task is an entry whose Object has a Kindoftask; the task configuration
    itself is an entry in the same list and has none.
    """
    tasks = {}
    for entry in _parse(xml_text).iter():
        meta = _named(entry, "MetaObject")
        obj = _named(entry, "Object")
        if meta is None or obj is None:
            continue
        kind = _named(obj, "Kindoftask")
        if kind is None:
            continue
        interval = _named(obj, "Interval")
        tasks[_text(_named(meta, "Name"))] = (
            _text(kind), _text(_named(interval, "Time")),
            _text(_named(interval, "Unit")))
    return tasks


def _parse(xml_text):
    """The document's root, parsed the same way on IronPython and CPython.

    Encoded to UTF-8 bytes with any declaration dropped: a declaration that
    says utf-16 on text that is already decoded is a lie, and IronPython's
    parser wants bytes.
    """
    if isinstance(xml_text, bytes):
        xml_text = xml_text.decode("utf-8-sig")
    text = DECLARATION.sub(u"", xml_text.lstrip(u"﻿"), count=1)
    return ET.fromstring(text.encode("utf-8"))


def _named(element, name):
    """The direct child with this Name attribute, or None."""
    if element is None:
        return None
    for child in element:
        if child.get("Name") == name:
            return child
    return None


def _text(element):
    if element is None or element.text is None:
        return u""
    return element.text.strip()
