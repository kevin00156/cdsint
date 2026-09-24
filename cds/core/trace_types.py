# -*- coding: utf-8 -*-
"""The types read_value() reports, as a trace needs them: sizes and roles.

Step 5 of `plc trace` reads every variable a job names (SPEC 6.8), and what
comes back is an IEC literal such as 'INT#3'. The type in front of the '#'
is what sizes the controller's ring, and what says whether a variable may
trigger the trace or be its record condition. Pure Python, so CI tests it.
"""
from __future__ import print_function

BOOL = "BOOL"

# Bytes per value of each IEC elementary type. A type not here has no size
# cdsint knows, and a variable of it is refused rather than guessed at: an
# estimate that is too small is how a controller runs out of memory.
SIZES = dict((name, size) for size, names in (
    (1, "BOOL BYTE SINT USINT"),
    (2, "WORD INT UINT"),
    (4, "DWORD DINT UDINT REAL TIME TOD DATE DT"),
    (8, "LWORD LINT ULINT LREAL LTIME")) for name in names.split())

# The short and long literal prefixes IEC 61131-3 allows for the time types,
# each to the name SIZES uses.
ALIASES = {"T": "TIME", "LT": "LTIME", "TIME_OF_DAY": "TOD", "D": "DATE",
           "DATE_AND_TIME": "DT"}

# What a trigger level can be compared with. BOOL is not among them: how the
# IDE takes a boolean level is not known (docs/trace-research.md 4); nor are
# the time types, whose level no run has tried.
NUMERIC = frozenset("SINT USINT INT UINT DINT UDINT LINT ULINT REAL LREAL "
                    "BYTE WORD DWORD LWORD".split())

# A BOOL's literal carries no type prefix in IEC 61131-3, so a bare TRUE or
# FALSE is the one value that names its type without a '#'.
BOOL_WORDS = ("TRUE", "FALSE")


def type_of(shown):
    """The IEC type a read_value() answer names, upper case, or None."""
    text = (shown or "").strip()
    if "#" in text:
        prefix = text.split("#", 1)[0].strip().upper()
        return ALIASES.get(prefix, prefix)
    if text.upper() in BOOL_WORDS:
        return BOOL
    return None


def refusals(job, shown):
    """[(name, why)] for each variable the job cannot use as what it read.

    `shown` maps each lower-case name trace_job.named() gives to what
    read_value() answered. A recorded variable needs a size, a trigger a
    number, a condition a BOOL (SPEC 6.8).
    """
    found = []
    for name in job["variables"]:
        said = shown[name.lower()]
        if type_of(said) not in SIZES:
            found.append((name, "read back as %s, a type with no size cdsint "
                          "knows, so the controller memory it needs cannot "
                          "be estimated" % _said(said)))
    trigger = (job.get("trigger") or {}).get("variable")
    if trigger and type_of(shown[trigger.lower()]) not in NUMERIC:
        found.append((trigger, "is the trigger and read back as %s; a trigger "
                      "needs a numeric type" % _said(shown[trigger.lower()])))
    condition = job.get("record_condition")
    if condition and type_of(shown[condition.lower()]) != BOOL:
        found.append((condition, "is the record_condition and read back as "
                      "%s, not a BOOL" % _said(shown[condition.lower()])))
    return found


def _said(shown):
    return "'%s' (type %s)" % (shown, type_of(shown) or "unknown")
