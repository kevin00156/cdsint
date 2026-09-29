# -*- coding: utf-8 -*-
"""The types read_value() reports, as a trace needs them: sizes and roles.

Step 5 of `plc trace` reads every variable a job names (SPEC 6.8), and what
comes back is an IEC literal such as 'INT#3'. The type in front of the '#'
is what sizes the controller's ring, and what says whether a variable may
trigger the trace or be its record condition. An enumeration's value names
no such type, so its size comes from the IDE instead (base_of). Pure Python,
so CI tests it.
"""
from __future__ import print_function

import re

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
# the time types, whose level no run has tried; nor is an enumeration, which
# no run has triggered on either.
NUMERIC = frozenset("SINT USINT INT UINT DINT UDINT LINT ULINT REAL LREAL "
                    "BYTE WORD DWORD LWORD".split())

# A BOOL's literal carries no type prefix in IEC 61131-3, so a bare TRUE or
# FALSE is the one value that names its type without a '#'.
BOOL_WORDS = ("TRUE", "FALSE")

# How read_value() shows a member of an enumeration: the type's name, a dot,
# the member, and no namespace even for a library's type (research 14). A
# value that is no member reads as its base type's literal, 'INT#3', which
# type_of() takes as it is.
ENUM_VALUE = re.compile(r"^([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\.[A-Za-z_]\w*$")

# The class the IDE's saved trace configuration gives a variable, for each of
# the twelve types an enumeration can be based on; research 14 measured every
# one. Other classes are not listed because nothing here reads them.
ENUM_BASES = {2: "BYTE", 3: "WORD", 4: "DWORD", 5: "LWORD", 6: "SINT",
              7: "INT", 8: "DINT", 9: "LINT", 10: "USINT", 11: "UINT",
              12: "UDINT", 13: "ULINT"}


def type_of(shown):
    """The IEC type a read_value() answer names, upper case, or None."""
    text = (shown or "").strip()
    if "#" in text:
        prefix = text.split("#", 1)[0].strip().upper()
        return ALIASES.get(prefix, prefix)
    if text.upper() in BOOL_WORDS:
        return BOOL
    return None


def enum_of(shown):
    """The enumeration a read_value() answer is a member of, or None."""
    match = ENUM_VALUE.match((shown or "").strip())
    return match.group(1) if match else None


def base_of(reported):
    """The base type the IDE reports for an enumeration, or None.

    `reported` is the variable's settings in the trace configuration the IDE
    saved before the download ({"Class": "7", "Size": "2", ...}). The class
    names the type and the size has to be that type's SIZES entry: the two
    are separate facts, and when they disagree neither is trusted.
    """
    try:
        kind = ENUM_BASES.get(int(reported["Class"]))
        size = int(reported["Size"])
    except (KeyError, TypeError, ValueError):
        return None
    return kind if kind and SIZES[kind] == size else None


def recorded_type(shown, reported):
    """The type that sizes a variable in the controller's ring, or None.

    What its literal names; for a member of an enumeration, which names no
    type, the base type the IDE reports.
    """
    if enum_of(shown):
        return base_of(reported)
    return type_of(shown)


def refusals(job, shown, reported):
    """[(name, why)] for each variable the job cannot use as what it read.

    `shown` maps each lower-case name trace_job.named() gives to what
    read_value() answered, `reported` each recorded one to its settings in
    the IDE's saved trace configuration. A recorded variable needs a size, a
    trigger a number, a condition a BOOL (SPEC 6.8).
    """
    found = []
    for name in job["variables"]:
        said, settings = shown[name.lower()], reported.get(name.lower())
        if recorded_type(said, settings) not in SIZES:
            found.append((name, _unsized(said, settings)))
    trigger = (job.get("trigger") or {}).get("variable")
    if trigger and type_of(shown[trigger.lower()]) not in NUMERIC:
        found.append((trigger, "is the trigger and read back as %s; a trigger "
                      "needs a numeric type" % _said(shown[trigger.lower()])))
    condition = job.get("record_condition")
    if condition and type_of(shown[condition.lower()]) != BOOL:
        found.append((condition, "is the record_condition and read back as "
                      "%s, not a BOOL" % _said(shown[condition.lower()])))
    return found


def _unsized(shown, settings):
    enum = enum_of(shown)
    if enum is None:
        return ("read back as %s, a type with no size cdsint knows, so the "
                "controller memory it needs cannot be estimated"
                % _said(shown))
    given = ("class %s, size %s" % (settings.get("Class"), settings.get("Size"))
             if settings else "no class or size")
    return ("read back as %s, and the trace configuration the IDE saved "
            "gives it %s, which is none of the integer types an enumeration "
            "can be based on; without its base type the controller memory it "
            "needs cannot be estimated" % (_said(shown), given))


def _said(shown):
    enum = enum_of(shown)
    if enum:
        return "'%s' (a member of enumeration %s)" % (shown, enum)
    return "'%s' (type %s)" % (shown, type_of(shown) or "unknown")
