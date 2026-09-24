# -*- coding: utf-8 -*-
"""A saved trace CSV: read it, and judge whether any samples were lost.

Timestamps alone cannot tell a lost sample from a cycle the task never ran,
so the judgement is by size (SPEC 6.8 "Completeness"): the share of samples
the span should hold, plus the longest silence. A task that started late on
a non-realtime controller leaves a gap of a few periods; a controller ring
that overflowed leaves one at least as long as the IDE's fetch interval.

The file format is in docs/trace-research.md section 5. Pure Python
(PRINCIPLES.md 4), so CI tests it on files, without an IDE.
"""
from __future__ import print_function

import io
import re

# An interval this much longer than the sampling period is listed as a gap.
# Jitter on a non-realtime controller stretches one interval by a fraction of
# a period without losing a cycle; half a period more than that means at
# least one cycle is missing.
GAP_PERIODS = 1.5

# The CSV's `Flags` is a bit field. These two bits name the timestamp unit
# (research section 5); other bits say other things, 4 being set on every
# file recorded under a record condition (research 13.4, Flags 36).
FLAG_UNITS = {32: "us", 16: "ms"}

MICROSECONDS_PER = {"us": 1, "ms": 1000}

VARIABLE = re.compile(r"^\d+\.Variable$")
SETTING = re.compile(r"^\d+\.")


class Unreadable(ValueError):
    """The file is not the shape `save()` writes; the message names the line."""


def read_csv(path):
    """{"header": {key: value}, "variables": [{name, timestamps, values}]}.

    The header is every `key; value` line before the first variable. A
    variable's own settings lines (`0.Class; 12` ...) are not kept: nothing
    here uses them, and the .trace file carries them in full.
    """
    header = {}
    variables = []
    with io.open(path, encoding="utf-8-sig") as handle:
        for number, raw in enumerate(handle, 1):
            line = raw.rstrip(u"\r\n")
            if line.strip():
                _take(line, number, header, variables)
    return {"header": header, "variables": variables}


def _take(line, number, header, variables):
    """Put one line where it belongs, or refuse it by line number."""
    if line.startswith(u";"):
        if not variables:
            raise Unreadable("line %d is a sample before any variable" % number)
        _sample(line, number, variables[-1])
        return
    if u";" not in line:
        raise Unreadable("line %d is not 'key; value': %r" % (number, line))
    key, value = [part.strip() for part in line.split(u";", 1)]
    if VARIABLE.match(key):
        variables.append({"name": value, "timestamps": [], "values": []})
    elif not variables:
        header[key] = value
    elif not SETTING.match(key):
        raise Unreadable("line %d is neither a sample nor a setting of %s: %r"
                         % (number, variables[-1]["name"], line))


def _sample(line, number, variable):
    parts = line.split(u";", 2)
    try:
        timestamp = int(parts[1].strip())
    except (IndexError, ValueError):
        raise Unreadable("line %d has no whole-number timestamp: %r"
                         % (number, line))
    variable["timestamps"].append(timestamp)
    variable["values"].append(parts[2].strip() if len(parts) > 2 else u"")


def file_unit(header):
    """"us" or "ms" from the header's Flags, or None when not exactly one
    unit bit is set or Flags is not a number."""
    try:
        flags = int((header.get("Flags") or "").strip(), 0)
    except ValueError:
        return None
    units = [unit for bit, unit in FLAG_UNITS.items() if flags & bit]
    return units[0] if len(units) == 1 else None


def to_file_units(period_us, unit):
    """A period in microseconds, in the unit the file's timestamps use.

    Stays an int when it divides evenly, so a 4 ms period in a millisecond
    file compares as 4, not 4.0.
    """
    scale = MICROSECONDS_PER[unit]
    if period_us % scale == 0:
        return period_us // scale
    return float(period_us) / scale


def judge(variables, period, min_complete, max_gap_periods):
    """(one SPEC 6.8 report row per variable, whether the run is complete).

    `period` is the sampling period in the file's timestamp unit. The run is
    complete when every variable reaches `min_complete` and none has an
    interval longer than `max_gap_periods` periods. A file with no variables
    is not complete: nothing recorded is not the same as nothing lost.
    """
    rows = [_row(variable, period) for variable in variables]
    limit = max_gap_periods * period
    complete = bool(rows) and all(
        row["complete"] >= min_complete and row["longest_interval"] <= limit
        for row in rows)
    return rows, complete


def counted(variables):
    """The report rows of samples that are not one per cycle.

    A record condition keeps only the cycles where it held, so nothing says
    how many samples there should have been: `expected`, `complete` and
    `gaps` are None rather than numbers that would read as a judgement.
    """
    rows = []
    for variable in variables:
        stamps = variable["timestamps"]
        rows.append({"name": variable["name"], "samples": len(stamps),
                     "expected": None, "complete": None, "gaps": None,
                     "longest_interval": _longest(stamps)})
    return rows


def _longest(stamps):
    return max([later - earlier
                for earlier, later in zip(stamps, stamps[1:])] or [0])


def _row(variable, period):
    stamps = variable["timestamps"]
    intervals = list(zip(stamps, stamps[1:]))
    expected = (stamps[-1] - stamps[0]) // period + 1 if stamps else 0
    return {
        "name": variable["name"],
        "samples": len(stamps),
        "expected": int(expected),
        "complete": round(float(len(stamps)) / expected, 4) if expected else 0.0,
        "gaps": [[earlier, later] for earlier, later in intervals
                 if later - earlier > GAP_PERIODS * period],
        "longest_interval": _longest(stamps),
    }
