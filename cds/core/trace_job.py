# -*- coding: utf-8 -*-
"""The `plc trace` job file: what it may hold, and what it names.

The job file is JSON a person or an agent writes by hand (SPEC 6.8), so it is
checked the way the settings file is (SPEC 4.4): an unknown key, a missing
required key or a value of the wrong shape refuses the whole run, before any
IDE starts, and the refusal says what was found and what is allowed.

Pure Python (PRINCIPLES.md 4): the CLI checks the file before it spends an
IDE on it, and the engine checks the job it is handed again with the same
function. Sizing and pacing the run is cds/core/trace_run.py.
"""
from __future__ import print_function

import json
import re

# IronPython 2.7 has two string types and json hands back the unicode one;
# CPython 3 has one. Likewise `long` exists only in 2.7. Each set collapses
# to whatever this interpreter has.
TEXT_TYPES = tuple(set([type(u""), type("")]))
NUMBER_TYPES = tuple(set([int, float, type(2 ** 64)]))
INTEGER_TYPES = tuple(set([int, type(2 ** 64)]))

# What a value may be. The name is what a refusal prints, so it reads as the
# thing a person would type into the file rather than as a Python type.
TEXT = "a non-empty string"
NAMES = "a non-empty list of distinct variable paths, without Application."
SECONDS = "a number greater than 0"
FORMATS = "a non-empty list of distinct words from trace, csv and txt"
RESOLUTION = 'either "us" or "ms"'
COUNT = "a whole number of at least 1"
FRACTION = "a number from 0 to 1"
TRIGGER = ('an object: "variable" a path, "edge" "rising", "falling" or '
           '"both", "level" a number, "post_samples" a whole number of at '
           'least 1')
PATH = "one variable path, without Application."

FORMAT_WORDS = ("trace", "csv", "txt")
RESOLUTIONS = ("us", "ms")
EDGES = ("rising", "falling", "both")
TRIGGER_KEYS = ("variable", "edge", "level", "post_samples")

# The fields that judge completeness. With a record_condition the samples are
# not one per cycle, so there is nothing for them to judge (SPEC 6.8).
JUDGING = ("min_complete", "max_gap_periods")

# Marks the fields a job has to name; there is no guess for what to record.
REQUIRED = object()
# Marks the fields that change what a run is when given, so there is no
# default to fill in: absent means the run does without.
OPTIONAL = object()

# name, kind, default, what it is for. The only place a default lives.
SCHEMA = (
    ("task", TEXT, REQUIRED, "the cyclic IEC task to sample in"),
    ("variables", NAMES, REQUIRED,
     "paths as read_value() takes them, e.g. PRG_X.var or GVL.var"),
    ("duration_s", SECONDS, REQUIRED, "how long to record, in seconds"),
    ("out", TEXT, REQUIRED,
     "output path without extension; existing files are overwritten"),
    ("formats", FORMATS, ("trace", "csv"), "which files to save"),
    ("resolution", RESOLUTION, "us", "timestamp unit in the files"),
    ("every_n_cycles", COUNT, 1, "sample every Nth task cycle"),
    ("min_complete", FRACTION, 0.99,
     "completeness below which the run fails"),
    ("max_gap_periods", COUNT, 20,
     "a gap longer than this many sampling periods fails the run"),
    ("trigger", TRIGGER, OPTIONAL,
     "stop by itself post_samples after variable crosses level on edge; "
     "duration_s is then the longest wait for that"),
    ("record_condition", PATH, OPTIONAL,
     "a BOOL variable; record only the cycles where it is TRUE"),
)

KINDS = dict((name, kind) for name, kind, _d, _m in SCHEMA)


def normalise(job):
    """(the job with every default filled in, None), or (None, problem).

    Never raises on what a person wrote: the caller turns the problem into
    a refusal, and a traceback is not a refusal.
    """
    if not isinstance(job, dict):
        return None, _refusal("the job is not a JSON object, it is %s"
                              % _shown(job))
    unknown = sorted(key for key in job if key not in KINDS)
    if unknown:
        return None, _refusal("%s is not a job field cdsint knows"
                              % _shown(unknown[0]))
    result = {}
    for name, kind, default, _meaning in SCHEMA:
        if name in job:
            value, problem = CHECKS[kind](job[name])
            if problem is not None:
                return None, _refusal("%s wants %s, not %s%s" % (
                    name, kind, _shown(job[name]), problem))
            result[name] = value
        elif default is REQUIRED:
            return None, _refusal("%s is required and missing" % name)
        elif default is not OPTIONAL:
            result[name] = _copy(default)
    problem = _together(job, result)
    if problem:
        return None, _refusal(problem)
    return result, None


def _together(job, result):
    """What the fields refuse in each other's company. None if nothing.

    Judged on `job`, what was written, not on `result`, where the defaults
    are already in: a min_complete somebody wrote beside a record_condition
    is a mistake, one the schema filled in is not. The judging fields leave
    the result with a condition, so a normalised job normalises again to
    itself, which is how the engine re-checks what the CLI already did.
    """
    if "trigger" in result and "record_condition" in result:
        return ("trigger and record_condition cannot be given together: "
                "they were only measured apart")
    if "record_condition" not in result:
        return None
    given = [name for name in JUDGING if name in job]
    if given:
        return ("%s cannot be given with record_condition: its samples are "
                "not one per cycle, so completeness is not judged"
                % " and ".join(given))
    for name in JUDGING:
        del result[name]
    return None


def table():
    """The schema as lines a person can read, one field per line."""
    lines = []
    for name, kind, default, meaning in SCHEMA:
        shown = ("required" if default is REQUIRED
                 else "optional" if default is OPTIONAL
                 else "default " + json.dumps(_copy(default)))
        lines.append("  %-16s %s; %s. %s" % (name, kind, shown, meaning))
    return lines


def named(job):
    """Every variable path the job names, each once, recorded ones first.

    The trigger's variable and the condition are read in step 5 like the
    recorded ones (SPEC 6.8), and may be among them.
    """
    names = list(job["variables"])
    seen = set(name.lower() for name in names)
    for name in [(job.get("trigger") or {}).get("variable"),
                 job.get("record_condition")]:
        if name and name.lower() not in seen:
            names.append(name)
            seen.add(name.lower())
    return names


# -- the checking ----------------------------------------------------------
# Each check returns (value in the form the engine uses, None) or
# (None, extra text): the extra is appended to "X wants KIND, not VALUE" when
# the kind alone does not say which element was wrong.

def _text(value):
    if isinstance(value, TEXT_TYPES) and value.strip():
        return value, None
    return None, ""


def _is_number(value):
    # bool is an int in Python, and `"duration_s": true` is a mistake worth
    # naming rather than reading as one second.
    return isinstance(value, NUMBER_TYPES) and not isinstance(value, bool)


def _seconds(value):
    if _is_number(value) and value > 0:
        return float(value), None
    return None, ""


def _fraction(value):
    if _is_number(value) and 0 <= value <= 1:
        return float(value), None
    return None, ""


def _count(value):
    if (isinstance(value, INTEGER_TYPES) and not isinstance(value, bool)
            and value >= 1):
        return int(value), None
    return None, ""


def _resolution(value):
    if isinstance(value, TEXT_TYPES) and value in RESOLUTIONS:
        return value, None
    return None, ""


def _words(value, allowed):
    """A non-empty list of distinct strings, each passing `allowed`."""
    if not isinstance(value, list) or not value:
        return None, ""
    seen = set()
    for word in value:
        problem = allowed(word)
        if problem is not None:
            return None, " (%s %s)" % (_shown(word), problem)
        # CODESYS names are case-insensitive, so PRG_X.a and prg_x.A are
        # the same variable recorded twice.
        if word.lower() in seen:
            return None, " (%s appears twice)" % _shown(word)
        seen.add(word.lower())
    return list(value), None


def _variable(word):
    """Why `word` is not a variable path, or None."""
    if not isinstance(word, TEXT_TYPES) or not word.strip():
        return "is not a variable path"
    # read_value() resolves names inside the application it was asked on,
    # so an "Application." prefix names a variable that is not there.
    if word.lower().startswith("application."):
        return "carries the application prefix; drop Application."
    return None


# A dotted path with constant indices: what read_value() and the trace take
# as one variable. A space or an operator makes it an expression.
SINGLE_PATH = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*|\[\d+(,\d+)*\])*$")


def _single(word):
    """Why `word` is not one variable, or None. An expression is refused
    here because the IDE takes one as a condition and start() then fails
    naming nothing (docs/trace-research.md 13.4)."""
    problem = _variable(word)
    if problem is None and not SINGLE_PATH.match(word):
        return "is not a single variable path"
    return problem


def _path(value):
    problem = _single(value)
    return (value, None) if problem is None else (None, " (%s)" % problem)


def _trigger(value):
    """The trigger object: exactly TRIGGER_KEYS, each passing its check."""
    if not isinstance(value, dict):
        return None, ""
    for key in sorted(value):
        if key not in TRIGGER_KEYS:
            return None, " (%s is not a trigger key)" % _shown(key)
    for key in TRIGGER_KEYS:
        if key not in value:
            return None, " (%s is missing)" % key
        problem = TRIGGER_CHECKS[key](value[key])
        if problem is not None:
            return None, " (%s %s %s)" % (key, _shown(value[key]), problem)
    return dict((key, value[key]) for key in TRIGGER_KEYS), None


def _edge(word):
    if isinstance(word, TEXT_TYPES) and word in EDGES:
        return None
    return "is not one of %s" % ", ".join(EDGES)


def _level(value):
    # The IDE converts the level to the trigger variable's type; a bool is
    # not one it was seen to take (docs/trace-research.md 4).
    return None if _is_number(value) else "is not a number"


def _post_samples(value):
    return None if _count(value)[1] is None else "is not " + COUNT


TRIGGER_CHECKS = {"variable": _single, "edge": _edge, "level": _level,
                  "post_samples": _post_samples}


def _format(word):
    if isinstance(word, TEXT_TYPES) and word in FORMAT_WORDS:
        return None
    return "is not one of %s" % ", ".join(FORMAT_WORDS)


CHECKS = {
    TEXT: _text,
    NAMES: lambda value: _words(value, _variable),
    SECONDS: _seconds,
    FORMATS: lambda value: _words(value, _format),
    RESOLUTION: _resolution,
    COUNT: _count,
    FRACTION: _fraction,
    TRIGGER: _trigger,
    PATH: _path,
}


def _copy(default):
    """Tuples become lists: the schema holds list defaults immutable."""
    return list(default) if isinstance(default, tuple) else default


def _shown(value):
    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        return repr(value)


def _refusal(problem):
    return u"\n".join([u"cannot use the job: %s" % problem, u"",
                       u"The job fields:"] + table())
