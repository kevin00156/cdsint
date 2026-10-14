# -*- coding: utf-8 -*-
"""trace list, job, apply, save and show: a trace's definition and data.

None of these touches a PLC. list says which traces the project has, where
they sit and what each records, so a trace can be named without knowing the
person's folders. job and apply move what a trace records between
a trace object and a job file, so a person can pick variables in the IDE and
an agent can record them with plc trace, or the other way round. save writes
what a trace in this IDE recorded; show loads a saved trace into a trace
the caller names, for a person to look at. The last two are the watcher's
only: recorded data lives in the IDE that recorded it (cds/ide/entries.py
HEADLESS_REFUSES).

apply saves the project, as import does: in the --project form nothing
else would, and the change would go with the IDE that made it. show leaves
the project unsaved: a trace holding a loaded file is for looking at, and
the person whose IDE it is decides whether that is kept.

The function names avoid `trace`: this file is exec'd into the namespace
CODESYS gives its scripts, where `trace` is the trace plug-in, which the
bodies borrow by that name (engine/entry_plc.py record says the same).
"""
from __future__ import print_function

import json
import os

from cds.core import dialogs, trace_job, trace_samples
from engine import backup, entry, ide_private, plc_crc, plc_trace_verdict
from engine import trace_config, trace_objects, trace_plugin, unhandled
from engine.ide_read import guid_of, name_of, parent_of
from engine.plc_trip import one_line

# The flags this run was given, put here by cds/ide/silent.py once this
# module's own code has run (silent.ARGS_GLOBAL).
command_args = {}

APPLY_QUESTION = ("This replaces what trace object %s records with the job "
                  "file's definition, creating it %s if there is none, and "
                  "saves the project.\n\nProceed?")
SHOW_QUESTION = ("This loads %s into trace object %s, which replaces what %s "
                 "records with the file's definition. The project is changed "
                 "in memory and not saved.\n\nProceed?")

# What a trace someone else recorded is judged against: the job's own
# defaults, since nobody wrote limits for it (SPEC 6.8 "Completeness").
JUDGING = dict((name, default) for name, _kind, default, _meaning
               in trace_job.SCHEMA if name in trace_job.JUDGING)

DEFAULT_FORMATS = ("trace", "csv")

NO_PROJECT = "'projects' object not found or no project open"

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


def list_traces():
    """trace list: every trace object, its whole path, and what it records.

    A trace that cannot be read is still listed, with why: its name and
    place are what the caller came for, and they need no private member.
    An object that will not say what it is might be a trace, so the list
    is not ok then (SPEC D11, D13): the rows are what could be seen.
    """
    unhandled.start()
    _args, project, refused = _inputs("list")
    if refused:
        return refused
    rows = sorted((_listed(project, obj)
                   for obj in trace_objects.every(project)),
                  key=lambda row: row["path"].lower())
    summary = "trace list: %d trace object(s)" % len(rows)
    if unhandled.any_so_far():
        summary += " -- " + unhandled.summary()
    return entry.result(
        not unhandled.any_so_far(), summary, action="list", traces=rows,
        failed_objects=unhandled.names())


def _listed(project, obj):
    path = trace_objects.path_of(project, obj)
    row = {"name": path.rsplit("/", 1)[-1], "path": path,
           "task": None, "variables": [], "left_out": [], "unread": None}
    api, problem = trace_objects.scripted(globals(), project, obj)
    if problem:
        row["unread"] = problem
        return row
    try:
        definition, left_out = trace_config.describe(
            api, entry.borrowed(globals(), "Resolution"))
    except Exception as exc:
        row["unread"] = one_line(exc) or type(exc).__name__
        return row
    row.update(definition, left_out=left_out)
    return row


def to_job():
    """trace job: what a trace object records, as a job file's definition."""
    unhandled.start()
    args, project, refused = _inputs("job")
    if refused:
        return refused
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
        try:
            _write_json(out, definition)
        except (IOError, OSError) as exc:
            return _failed("job", "%s could not be written: %s"
                           % (out, one_line(exc)), job=definition,
                           left_out=left_out, usable=usable)
    return entry.result(
        True, "trace job: %s records %d variable(s) on task %s"
        % (args["name"], len(definition["variables"]), definition["task"]),
        action="job", name=args["name"], job=definition, left_out=left_out,
        usable=usable, file=out, failed_objects=unhandled.names())


def from_job():
    """trace apply: make a trace object record a job file's definition.

    The definition, the name and the folder are checked before the
    question: each check only reads, and a refusal for any of them is worth
    more than a question whose yes leads only to it.
    """
    from engine.codesys_ui import ask_yes_no
    unhandled.start()
    args, project, refused = _inputs("apply")
    if refused:
        return refused
    name = args.get("name")
    definition, problem = trace_job.normalise_definition(args.get("job"))
    if problem:
        return _failed("apply", problem)
    existing, problem = _existing_trace(project, name)
    if problem:
        return _failed("apply", problem)
    folder, problem = _the_folder(project, args.get("folder"), existing)
    if problem:
        return _failed("apply", problem)
    where = trace_objects.path_of(project, folder if folder is not None
                                  else project.active_application)
    if not ask_yes_no(dialogs.CONFIRM_TRACE_APPLY,
                      APPLY_QUESTION % (name, "in " + where)):
        return _failed("apply", "not confirmed")
    api, replaced, problem = _the_trace_to_apply(project, name, definition,
                                                 existing, folder)
    if problem:
        return _failed("apply", problem)
    problem = trace_config.configure(api, definition,
                                     entry.borrowed(globals(), "Resolution"))
    if problem:
        # The old variables are gone by now (configure clears first), so
        # the report is the one place left that says what they were.
        return _failed("apply", "%s could not be configured: %s"
                       % (name, problem), replaced=replaced or [])
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


def _existing_trace(project, name):
    """(the trace called `name`, or None if there is none, None), or why
    `name` cannot be applied to.

    A name that belongs to something else is refused rather than created
    beside it: two objects of one name are what --name cannot tell apart.
    """
    traces, others = trace_objects.named(project, name)
    if len(traces) > 1:
        return None, trace_objects.several(project, name, traces)
    if traces:
        return traces[0], None
    if others:
        return None, ("%s is not a trace object%s"
                      % (name, trace_objects.what_else(project, others)))
    return None, None


def _the_folder(project, wanted, existing):
    """(the folder a new trace goes in, or None, None), or (None, why).

    --folder places a trace apply creates; it never moves one, so a trace
    already somewhere else is refused rather than left where it is while
    the caller believes it was put in the folder. An empty --folder is a
    folder nobody can have, not a missing flag.
    """
    if wanted is None:
        return None, None
    folder, problem = trace_objects.folder_named(project, wanted)
    if problem or existing is None:
        return folder, problem
    if guid_of(parent_of(existing)) == guid_of(folder):
        return None, None
    return None, ("%s already exists at %s, and apply changes a trace where "
                  "it is: leave out --folder, or move it in the IDE"
                  % (name_of(existing),
                     trace_objects.path_of(project, existing)))


def _the_trace_to_apply(project, name, definition, existing, folder):
    """(settings, what it recorded before or None if new, None), or a why."""
    if existing is not None:
        api, problem = trace_objects.scripted(globals(), project, existing)
        if problem:
            return None, None, problem
        return api, [v.variable_name for v in api.variable_list], None
    api, problem = trace_objects.create(globals(), project.active_application,
                                        name, definition["task"])
    if problem is None and folder is not None:
        made, problem = trace_objects.find(project, name)
        problem = problem or trace_objects.move(project, made, folder)
    return api, None, problem


def save_data():
    """trace save: what a trace recorded in this IDE, written and judged.

    ok once the files are written. The judgement is reported, not gated
    on: nobody here chose this trace's buffers, and one left at the IDE's
    default keeps only its last few thousand samples (research 15.8).
    """
    unhandled.start()
    args, project, refused = _inputs("save")
    if refused:
        return refused
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
    """trace show: a saved trace, loaded into a trace the caller names.

    Loading replaces the target's definition with the file's (research
    15.6), so the caller names the target and confirms, as for apply. It
    never creates one: CODESYS adds no object while logged in, which is when
    a person most wants to look. What was loaded is read back from the
    editor, not from the object's settings: on the bench those still named
    the old variables straight after the load, and only caught up later.
    """
    from engine.codesys_ui import ask_yes_no
    unhandled.start()
    args, project, refused = _inputs("show")
    if refused:
        return refused
    name, path = args.get("name"), args.get("file")
    if not ask_yes_no(dialogs.CONFIRM_TRACE_SHOW,
                      SHOW_QUESTION % (path, name, name)):
        return _failed("show", "not confirmed")
    api, problem = trace_objects.reach(globals(), project, name)
    if problem:
        return _failed("show", problem)
    if not os.path.isfile(path):
        return _failed("show", "%s does not exist, so nothing was loaded"
                       % path)
    editor = api.open_editor()
    if editor.is_running:
        # Loading replaces what the trace records, mid-recording; plc trace
        # refuses the same trace for the same reason.
        return _failed("show", "%s is recording; stop it, or wait for it, "
                       "then run this again" % name)
    load = ide_private.loader_for(editor)
    if load is None:
        return _failed("show", (
            "this IDE's trace editor has no %s with a %s, the private "
            "members cdsint loads a trace file through (docs/trace-research."
            "md 15.6), so nothing was loaded"
            % (ide_private.EDITOR_VIEW, ide_private.LOAD_TRACE)))
    said = load(path)
    if said:
        return _failed("show", "the IDE could not load %s: %s"
                       % (path, one_line(said)))
    variables, problem = _loaded(project, editor)
    if problem:
        return _failed("show", problem)
    return entry.result(
        True, "trace show: %s loaded into %s, %d variable(s)"
        % (path, name, len(variables)),
        action="show", name=name, file=path, variables=variables,
        failed_objects=unhandled.names())


def _loaded(project, editor):
    """(the variables the editor now holds, None), or (None, why not)."""
    path = os.path.join(plc_crc.workspace(project.path), SHOWN_CSV)
    try:
        editor.save(plc_crc.forget(path))
        return trace_samples.variable_names(path), None
    except Exception as exc:
        return None, ("the file was loaded, but what it holds could not be "
                      "read back: " + one_line(exc))


def _inputs(action):
    """(this run's flags, the open project, None), or a failed result when
    this IDE cannot script traces or no project is open."""
    problem = trace_plugin.missing(globals())
    if problem:
        return None, None, _failed(action, problem)
    projects = entry.borrowed(globals(), "projects")
    project = projects.primary if projects is not None else None
    if project is None:
        return None, None, _failed(action, NO_PROJECT)
    return entry.flags(globals()), project, None


def _failed(action, problem, **data):
    return entry.result(False, "trace %s: %s" % (action, problem),
                        action=action, failed_objects=unhandled.names(),
                        **data)


def _write_json(path, definition):
    _ensure_directory(path)
    with open(path, "w") as handle:
        handle.write(json.dumps(definition, indent=1, sort_keys=True) + "\n")


def _ensure_directory(path):
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
