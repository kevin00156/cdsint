# -*- coding: utf-8 -*-
"""What a plc trace run found: its saved CSV, judged, as the report's rows.

The judging itself is cds/core/trace_samples.py, plain Python CI tests on
files. This is the engine's side of it: which file, which period in which
unit, the type read_value() reported for each row, and the sentence a
reader gets when a variable fell short (SPEC 6.8 "Completeness").
"""
from __future__ import print_function

from cds.core import trace_run, trace_samples
from engine.strings import safe_str


def judged(csv_path, period_us, job, types):
    """(report fields, None) or (report fields, why the run is not ok).

    The fields are `resolution`, `variables` and `complete`, filled in as far
    as the file allowed; `complete` is None for a run with a record
    condition, which fails only on a file holding no variables. `types` maps a lower-case variable name to what
    read_value() said its type was.
    """
    found = {"resolution": job["resolution"], "variables": [],
             "complete": False}
    try:
        saved = trace_samples.read_csv(csv_path)
    except (IOError, OSError, ValueError) as exc:
        return found, ("the trace was saved but %s could not be read: %s"
                       % (csv_path, safe_str(exc)))
    unit = trace_samples.file_unit(saved["header"])
    if unit is None:
        return found, ("%s names no timestamp unit cdsint knows (Flags %r)"
                       % (csv_path, saved["header"].get("Flags")))
    period = trace_samples.to_file_units(
        trace_run.sampling_us(period_us, job["every_n_cycles"]), unit)
    if "record_condition" in job:
        # Samples only where the condition held are not one per cycle, so
        # there is no count to judge them against (SPEC 6.8).
        rows, complete = trace_samples.counted(saved["variables"]), None
    else:
        rows, complete = _judge(saved["variables"], period, job)
    for row in rows:
        row["type"] = types.get(row["name"].lower())
    # The unit the file really has, not the one asked for: gaps and
    # intervals are in it, and `resolution` is what names it (SPEC 6.8).
    found.update(resolution=unit, variables=rows, complete=complete)
    if rows and complete is not False:
        return found, None
    return found, shortfall(saved["variables"], rows, period, unit, job)


def shortfall(variables, rows, period, unit, job):
    """Which variables fell short, with their numbers and the job's limits.

    Each variable is judged alone by the same judge, so the limits are
    applied in one place and this only reports what it found.
    """
    if not rows:
        return ("the saved samples hold no variables at all; nothing "
                "recorded is not the same as nothing lost")
    short = ["%s has %d of %d expected samples (%s), longest interval %s %s"
             % (row["name"], row["samples"], row["expected"], row["complete"],
                row["longest_interval"], unit)
             for variable, row in zip(variables, rows)
             if not _judge([variable], period, job)[1]]
    # The ring holds the whole recording, so the IDE cannot have lost these;
    # on the bench every such gap was a stretch where the controller ran no
    # cycle (docs/trace-research.md 13.6). The timestamps cannot prove it
    # for a given run, so the sentence says "most likely" and what to do.
    return ("samples are missing, and the files are written as the "
            "evidence: %s. The job wants completeness of at least %s and no "
            "interval over %d sampling periods (%s %s). The controller's "
            "ring held the whole recording, so these are most likely cycles "
            "the controller did not run, usually because its CPU was too "
            "busy; a controller in a VM or without a realtime kernel does "
            "this routinely. If that is expected, raise max_gap_periods or "
            "lower min_complete in the job; otherwise look at the task's "
            "cycle time and the controller's load"
            % ("; ".join(short), job["min_complete"], job["max_gap_periods"],
               job["max_gap_periods"] * period, unit))


def _judge(variables, period, job):
    return trace_samples.judge(variables, period, job["min_complete"],
                               job["max_gap_periods"])
