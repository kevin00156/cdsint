# -*- coding: utf-8 -*-
"""trace job, apply, save and show: a trace's definition and data, in and out.

None of these touches a PLC. job and apply move what a trace records between
a trace object and a job file, so a person can pick variables in the IDE and
an agent can record them with plc trace, or the other way round. save writes
what a trace in this IDE recorded; show loads a saved trace into this IDE
for a person to look at. The last two are the watcher's only: recorded data
lives in the IDE that recorded it (cds/ide/entries.py HEADLESS_REFUSES).

apply saves the project, as import does: in the --project form nothing
else would, and the change would go with the IDE that made it. show leaves
the project unsaved: cdsint_trace holding a loaded file is for looking at,
and the person whose IDE it is decides whether that is kept.

The function names avoid `trace`: this file is exec'd into the namespace
CODESYS gives its scripts, where `trace` is the trace plug-in, which the
bodies borrow by that name (engine/entry_plc.py record says the same).
"""
from __future__ import print_function

import json
import os

from cds.core import dialogs, trace_job, trace_samples
from engine import backup, entry, ide_private, plc_crc, plc_trace_verdict
from engine import trace_config, trace_objects, unhandled
from engine.plc_trace_setup import TRACE_NAME
from engine.plc_trip import one_line

# The flags this run was given, put here by cds/ide/silent.py once this
# module's own code has run (silent.ARGS_GLOBAL).
command_args = {}

APPLY_QUESTION = ("This replaces what trace object %s records with the job "
                  "file's definition, creating it if there is none, and "
                  "saves the project.\n\nProceed?")

# What a trace someone else recorded is judged against: the job's own
# defaults, since nobody wrote limits for it (SPEC 6.8 "Completeness").
JUDGING = dict((name, default) for name, _kind, default, _meaning
               in trace_job.SCHEMA if name in trace_job.JUDGING)

DEFAULT_FORMATS = ("trace", "csv")

# A trace that has not recorded since the IDE opened still lists its
# variables in the file, with no rows; judged as samples it would read as
# every cycle missing and blame the controller.
NO_SAMPLES = ("the trace holds no samples: it has not recorded in this IDE "
              "since it was opened, or its data was cleared. The files "
              "hold only its configuration")

# Where save writes the CSV it judges when the caller asked for none, and
# where show writes the one it reads what it loaded from.
WORKSPACE_CSV = "saved.csv"
SHOWN_CSV = "shown.csv"


def to_job():
    """trace job: what a trace object records, as a job file's definition."""
    unhandled.start()
    args, project = _inputs()
    api, problem = trace_objects.reach(globals(), project, args.get("name"))
    if problem:
        return _failed("job", problem)
    definition, left_out = trace_config.describe(
        api, entry.borrowed(globals(), "Resolution"))
    _, refusal = trace_job.normalise_definition(definition)
    usable = ("yes" if refusal is None
              else "no: plc trace would refuse it: " + refusal)
    out = args.get("out")
    if out:
        _write_json(out, definition)
    return entry.result(
        True, "trace job: %s records %d variable(s) on task %s"
        % (args["name"], len(definition["variables"]), definition["task"]),
        action="job", name=args["name"], job=definition, left_out=left_out,
        usable=usable, file=out, failed_objects=unhandled.names())


def from_job():
    """trace apply: make a trace object record a job file's definition."""
    from engine.codesys_ui import ask_yes_no
    unhandled.start()
    args, project = _inputs()
    name = args.get("name")
    if not ask_yes_no(dialogs.CONFIRM_TRACE_APPLY, APPLY_QUESTION % name):
        return _failed("apply", "not confirmed")
    definition, problem = trace_job.normalise_definition(args.get("job"))
    if problem:
        return _failed("apply", problem)
    api, replaced, problem = _the_trace_to_apply(project, name, definition)
    if problem:
        return _failed("apply", problem)
    problem = trace_config.configure(api, definition,
                                     entry.borrowed(globals(), "Resolution"))
    if problem:
        return _failed("apply", "%s could not be configured: %s"
                       % (name, problem))
    created = replaced is None
    summary = ("trace apply: %s %s, recording %d variable(s) on task %s"
               % (name, "created" if created else "replaced",
                  len(definition["variables"]), definition["task"]))
    problem = backup.save_project(entry.borrowed(globals(), "projects"))
    if problem:
        summary += " -- but the project was not saved: " + problem
    return entry.result(
        problem is None, summary, action="apply", name=name, created=created,
        replaced=replaced or [], variables=definition["variables"],
        failed_objects=unhandled.names())


def _the_trace_to_apply(project, name, definition):
    """(settings, what it recorded before or None if new, None), or a why.

    A name that belongs to something else is refused rather than created
    beside it: two objects of one name are what --name cannot tell apart.
    """
    traces, others = trace_objects.named(project, name)
    if len(traces) > 1:
        return None, None, trace_objects.several(name, traces)
    if traces:
        api, problem = trace_objects.scripted(globals(), project, traces[0])
        if problem:
            return None, None, problem
        return api, [v.variable_name for v in api.variable_list], None
    if others:
        return None, None, ("%s is not a trace object%s"
                            % (name, trace_objects.what_else(others)))
    api, problem = trace_objects.create(globals(), project.active_application,
                                        name, definition["task"])
    return api, None, problem


def save_data():
    """trace save: what a trace recorded in this IDE, written and judged.

    ok once the files are written. The judgement is reported, not gated
    on: nobody here chose this trace's buffers, and one left at the IDE's
    default keeps only its last few thousand samples (research 15.8).
    """
    unhandled.start()
    args, project = _inputs()
    api, problem = trace_objects.reach(globals(), project, args.get("name"))
    if problem:
        return _failed("save", problem)
    files, csv_path, problem = _saved(project, api, args)
    if problem:
        return _failed("save", problem)
    found, why = _judged(project, api, csv_path)
    return entry.result(
        True, "trace save: %s written to %s" % (
            args["name"], ", ".join(sorted(files.values()))),
        action="save", name=args["name"], files=files, why=why,
        failed_objects=unhandled.names(), **found)


def _saved(project, api, args):
    """(files by kind, the CSV to judge, None), or (None, None, why not)."""
    formats = args.get("formats") or list(DEFAULT_FORMATS)
    files = dict((kind, args["out"] + "." + kind) for kind in formats)
    csv_path = files.get("csv") or os.path.join(
        plc_crc.workspace(project.path), WORKSPACE_CSV)
    editor = api.open_editor()
    path = None
    try:
        for path in sorted(set(list(files.values()) + [csv_path])):
            _ensure_directory(path)
            editor.save(plc_crc.forget(path))
    except Exception as exc:
        return None, None, "%s could not be written: %s" % (path,
                                                            one_line(exc))
    return files, csv_path, None


def _judged(project, api, csv_path):
    """(the report's judgement fields, why it falls short or None)."""
    definition, _left_out = trace_config.describe(
        api, entry.borrowed(globals(), "Resolution"))
    period, problem = trace_config.task_period_us(
        project, project.active_application, definition["task"])
    if problem:
        return {"complete": None, "variables": []}, (
            "the files are written, but completeness was not judged: "
            + problem)
    judging = dict(JUDGING, resolution=definition["resolution"],
                   every_n_cycles=definition["every_n_cycles"])
    if "record_condition" in definition:
        judging["record_condition"] = definition["record_condition"]
    found, why = plc_trace_verdict.judged(csv_path, period, judging, {})
    found["period_us"] = period
    rows = found["variables"]
    if rows and not any(row["samples"] for row in rows):
        return found, NO_SAMPLES
    return found, why


def show_data():
    """trace show: a saved trace, loaded into cdsint_trace for a person.

    Always cdsint_trace: loading replaces the target's definition with the
    file's (research 15.6), and that is only cdsint's to do to its own
    object. What was loaded is read back from the editor, not from the
    object's settings: on the bench those still named the old variables
    straight after the load, and only caught up later.
    """
    unhandled.start()
    args, project = _inputs()
    api, problem = _cdsint_trace(project)
    if problem:
        return _failed("show", problem)
    editor = api.open_editor()
    load = ide_private.loader_for(editor)
    if load is None:
        return _failed("show", (
            "this IDE's trace editor has no %s with a %s, the private "
            "members cdsint loads a trace file through (docs/trace-research."
            "md 15.6), so nothing was loaded"
            % (ide_private.EDITOR_VIEW, ide_private.LOAD_TRACE)))
    said = load(args.get("file"))
    if said:
        return _failed("show", "the IDE could not load %s: %s"
                       % (args.get("file"), one_line(said)))
    variables, problem = _loaded(project, editor)
    if problem:
        return _failed("show", problem)
    return entry.result(
        True, "trace show: %s loaded into %s, %d variable(s)"
        % (args["file"], TRACE_NAME, len(variables)),
        action="show", name=TRACE_NAME, file=args["file"],
        variables=variables, failed_objects=unhandled.names())


def _loaded(project, editor):
    """(the variables the editor now holds, None), or (None, why not)."""
    path = os.path.join(plc_crc.workspace(project.path), SHOWN_CSV)
    try:
        editor.save(plc_crc.forget(path))
        saved = trace_samples.read_csv(path)
    except Exception as exc:
        return None, ("the file was loaded, but what it holds could not be "
                      "read back: " + one_line(exc))
    return [each["name"] for each in saved["variables"]], None


def _cdsint_trace(project):
    """(cdsint_trace's settings, made if it is not there, None), or a why."""
    traces, others = trace_objects.named(project, TRACE_NAME)
    if traces:
        return trace_objects.reach(globals(), project, TRACE_NAME)
    if others:
        return None, ("%s is cdsint's name for its own trace object%s"
                      % (TRACE_NAME, trace_objects.what_else(others)))
    application = project.active_application
    task = trace_objects.first_task(application)
    if task is None:
        return None, ("the application has no task, and %s needs one to "
                      "exist in before the file replaces it" % TRACE_NAME)
    return trace_objects.create(globals(), application, TRACE_NAME, task)


def _inputs():
    """(this run's flags, the open project)."""
    return (entry.flags(globals()),
            entry.borrowed(globals(), "projects").primary)


def _failed(action, problem):
    return entry.result(False, "trace %s: %s" % (action, problem),
                        action=action, failed_objects=unhandled.names())


def _write_json(path, definition):
    _ensure_directory(path)
    with open(path, "w") as handle:
        handle.write(json.dumps(definition, indent=1, sort_keys=True) + "\n")


def _ensure_directory(path):
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
