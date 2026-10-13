# -*- coding: utf-8 -*-
"""trace job, apply, save and show, pressed the way the IDE side presses them.

Through cds/ide/entries.py, so the stand-in dialogs answer apply's question
and the result record is the one a caller reads. The two private members are
faked here (engine/ide_private.py): CPython has no .NET to reflect over, and
the real ones were measured on the bench (docs/trace-research.md 15.6-7).
"""
import io
import json

import pytest

from cds.ide import entries
from cds.ide import headless as ide_side
from engine import ide_private
from engine.codesys_constants import TYPE_GUIDS
from tests import plc_fakes
from tests.fakes import Node, Projects
from tests.plc_fakes import (   # noqa: F401  autouse fixtures
    fake_codesys_ui, keep_the_engine_loaded, workspace)

TASK = plc_fakes.TASK  # the sample CSV was recorded at its 1000 us


class TraceObjects(plc_fakes.TraceProject):
    """The open project, finding real nodes by name rather than names."""

    handle = 0

    def find(self, name, recursive=False):
        found, level = [], list(self.get_children(False))
        while level:
            node = level.pop(0)
            if node.get_name().lower() == name.lower():
                found.append(node)
            level.extend(node.get_children(False))
        return found


class NoScriptTraceObject(object):
    is_trace_object = False


class Bench(object):
    """One project with an application, a task, a folder and the trace
    plug-in; trace objects appear in the tree as `trace.create` makes them.
    """

    def __init__(self, monkeypatch, csv_text=None):
        self.log = []
        self.csv_text = (plc_fakes.read_data(plc_fakes.SAMPLE_CSV)
                         if csv_text is None else csv_text)
        task_config = Node("Task configuration", TYPE_GUIDS["task_config"],
                           [Node(TASK, TYPE_GUIDS["task"])])
        self.application = Node("Application", TYPE_GUIDS["application"],
                                [task_config,
                                 Node("TraceEnum", TYPE_GUIDS["folder"])])
        self.project = TraceObjects(
            [self.application], self.application,
            plc_fakes.read_data(plc_fakes.TASK_CONFIG_XML))
        self.apis = {}       # node guid -> the trace object's settings
        self.files = {}      # a saved .trace -> the CSV text it holds
        self.loads = []
        self.reachable = True
        self.online = False     # logged in: CODESYS adds no objects then
        monkeypatch.setattr(ide_private, "script_trace", self.script_trace)
        monkeypatch.setattr(ide_private, "loader_for", self.loader_for)

    # -- the IDE ----------------------------------------------------------

    def create(self, application, name, task):
        if self.online:
            # What create() hands back while the application is logged in
            # (docs/trace-research.md 15): no object, and no exception.
            return NoScriptTraceObject()
        api = plc_fakes.TraceApi(self.log, self.csv_text, None)
        api.task_name = task
        node = Node(name, TYPE_GUIDS["trace"], parent=application)
        application._children.append(node)
        self.apis[node.guid] = api
        return api

    def script_trace(self, tracer, handle, guid):
        return self.apis.get(guid) if self.reachable else None

    def loader_for(self, editor):
        """As measured: the load replaces what the editor holds at once, and
        reaches the trace object's settings only later, so a read straight
        after it finds the old ones (docs/trace-research.md 15.6)."""
        def load(path):
            self.loads.append(path)
            if path not in self.files:
                return "the file is not a trace"
            editor.csv_text = self.files[path]
            return None
        return load

    def globals(self):
        return {"system": plc_fakes.TraceSystem(self.log),
                "projects": Projects(self.project),
                "trace": self, "Resolution": plc_fakes.Resolution}

    def press(self, action, **args):
        return entries.answer(self.globals(), {
            "id": "1", "command": "trace " + action, "args": args},
            0.0)

    def trace_named(self, name):
        found = [n for n in self.project.find(name, True)
                 if n.type == TYPE_GUIDS["trace"]]
        return self.apis[found[0].guid] if found else None


@pytest.fixture
def bench(monkeypatch):
    return Bench(monkeypatch)


def definition(*variables, **more):
    job = {"task": TASK, "variables": list(variables) or ["PLC_PRG.n"],
           "resolution": "us", "every_n_cycles": 1}
    job.update(more)
    return job


# --- trace apply ---------------------------------------------------------------

def test_apply_creates_a_trace_that_job_reads_back(bench):
    applied = bench.press("apply", yes=True, name="T1",
                          job=definition("a.x", "a.y"))
    assert applied["ok"], applied["error"]
    assert applied["data"]["created"] is True
    read = bench.press("job", name="T1")
    assert read["ok"], read["error"]
    assert read["data"]["job"] == definition("a.x", "a.y")


def test_apply_replaces_what_an_existing_trace_held(bench):
    bench.press("apply", yes=True, name="T1", job=definition("old.a"))
    again = bench.press("apply", yes=True, name="T1", job=definition("new.b"))
    assert again["ok"], again["error"]
    assert again["data"]["created"] is False
    assert again["data"]["replaced"] == ["old.a"]
    assert bench.trace_named("T1").variables == ["new.b"]
    assert len(bench.project.find("T1", True)) == 1


def test_apply_without_yes_asks_instead_of_changing_the_project(bench):
    asked = bench.press("apply", name="T1", job=definition())
    assert not asked["ok"] and asked["needs_input"]
    assert bench.trace_named("T1") is None


def test_apply_onto_something_that_is_not_a_trace_is_refused(bench):
    refused = bench.press("apply", yes=True, name="TraceEnum",
                          job=definition())
    assert not refused["ok"]
    assert "TraceEnum" in refused["error"] and "folder" in refused["error"]


def test_apply_saves_the_project_it_changed(bench):
    applied = bench.press("apply", yes=True, name="T1", job=definition())
    assert applied["ok"], applied["error"]
    assert bench.project.saves == 1


def test_a_refused_apply_saves_nothing(bench):
    bench.press("apply", yes=True, name="TraceEnum", job=definition())
    assert bench.project.saves == 0


def test_an_apply_that_could_not_save_is_not_ok_and_says_why(bench):
    def refuse():
        raise IOError("the file is read-only")
    bench.project.save = refuse
    applied = bench.press("apply", yes=True, name="T1", job=definition())
    assert not applied["ok"]
    assert "not saved" in applied["error"]
    assert "read-only" in applied["error"]


# --- trace job -----------------------------------------------------------------

def test_job_on_a_name_that_is_no_trace_says_what_it_is(bench):
    refused = bench.press("job", name="TraceEnum")
    assert not refused["ok"]
    assert "no trace object named TraceEnum" in refused["error"]
    assert "folder" in refused["error"]


def test_job_leaves_out_switched_off_variables_and_says_so(bench):
    bench.press("apply", yes=True, name="T1", job=definition("a.x", "a.y"))
    bench.trace_named("T1").disabled = set(["a.y"])
    read = bench.press("job", name="T1")
    assert read["data"]["job"]["variables"] == ["a.x"]
    assert read["data"]["left_out"] == ["a.y"]


def test_job_writes_the_file_it_was_asked_for(bench, tmp_path):
    bench.press("apply", yes=True, name="T1", job=definition("a.x"))
    out = tmp_path / "t1.json"
    read = bench.press("job", name="T1", out=str(out))
    with io.open(str(out), encoding="utf-8") as handle:
        assert json.load(handle) == read["data"]["job"]


def test_job_says_when_plc_trace_would_refuse_what_it_wrote(bench):
    bench.press("apply", yes=True, name="T1", job=definition("a.x"))
    bench.trace_named("T1").variables = []
    read = bench.press("job", name="T1")
    assert read["ok"]
    assert "plc trace would refuse" in read["data"]["usable"]


def test_job_without_the_private_member_is_refused_by_name(bench):
    bench.press("apply", yes=True, name="T1", job=definition())
    bench.reachable = False
    refused = bench.press("job", name="T1")
    assert not refused["ok"]
    assert ide_private.CREATE_SCRIPT_TRACE in refused["error"]


# --- trace save ----------------------------------------------------------------

def test_save_writes_each_format_and_judges_the_samples(bench, tmp_path):
    bench.press("apply", yes=True, name="T1",
                job=definition(*plc_fakes.TRACED))
    out = str(tmp_path / "run")
    saved = bench.press("save", name="T1", out=out, formats=["csv", "trace"])
    assert saved["ok"], saved["error"]
    assert saved["data"]["files"] == {"csv": out + ".csv",
                                      "trace": out + ".trace"}
    assert saved["data"]["complete"] is True
    assert [row["name"] for row in saved["data"]["variables"]] == \
        plc_fakes.TRACED


def test_save_of_samples_with_gaps_is_still_ok_and_says_why(monkeypatch,
                                                            tmp_path):
    bench = Bench(monkeypatch, csv_text=plc_fakes.gapped_csv())
    bench.press("apply", yes=True, name="T1",
                job=definition(*plc_fakes.TRACED))
    saved = bench.press("save", name="T1", out=str(tmp_path / "run"))
    assert saved["ok"]
    assert saved["data"]["complete"] is False
    assert "samples are missing" in saved["data"]["why"]


def test_save_of_a_trace_that_never_recorded_is_ok(monkeypatch, tmp_path):
    header = u"".join(line for line in plc_fakes.read_data(
        plc_fakes.SAMPLE_CSV).splitlines(True) if not line.startswith(u";"))
    bench = Bench(monkeypatch, csv_text=header)
    bench.press("apply", yes=True, name="T1", job=definition())
    saved = bench.press("save", name="T1", out=str(tmp_path / "run"))
    assert saved["ok"], saved["error"]
    assert "holds no samples" in saved["data"]["why"]


def test_the_headless_launcher_refuses_save(bench):
    results = ide_side.run_commands(bench.globals(), [
        {"command": "trace save", "args": {"name": "T1", "out": "o"}}])
    assert not results[0]["ok"]
    assert "Recorded data lives only in the IDE" in results[0]["error"]


# --- trace show ----------------------------------------------------------------

def saved_trace(bench):
    """T1 in the project, and a saved .trace the loader knows."""
    bench.press("apply", yes=True, name="T1", job=definition())
    bench.files["C:/r.trace"] = plc_fakes.read_data(plc_fakes.SAMPLE_CSV)
    return "C:/r.trace"


def test_show_loads_into_the_named_trace_and_reports_what_it_loaded(bench):
    shown = bench.press("show", yes=True, name="T1", file=saved_trace(bench))
    assert shown["ok"], shown["error"]
    assert shown["data"]["name"] == "T1"
    assert shown["data"]["variables"] == plc_fakes.TRACED
    assert bench.loads == ["C:/r.trace"]


def test_show_without_yes_asks_and_loads_nothing(bench):
    asked = bench.press("show", name="T1", file=saved_trace(bench))
    assert not asked["ok"] and asked["needs_input"]
    assert bench.loads == []


def test_show_into_a_trace_that_is_not_there_creates_nothing(bench):
    refused = bench.press("show", yes=True, name="T9", file="C:/r.trace")
    assert not refused["ok"]
    assert "no trace object named T9" in refused["error"]
    assert bench.trace_named("T9") is None
    assert bench.trace_named("cdsint_trace") is None


def test_show_does_not_save_the_project(bench):
    path = saved_trace(bench)
    saves = bench.project.saves
    bench.press("show", yes=True, name="T1", file=path)
    assert bench.project.saves == saves


def test_show_passes_on_what_the_loader_said(bench):
    saved_trace(bench)
    shown = bench.press("show", yes=True, name="T1",
                        file="C:/not-a-trace.txt")
    assert not shown["ok"] and "the file is not a trace" in shown["error"]


def test_show_without_the_loader_is_refused_by_name(bench, monkeypatch):
    path = saved_trace(bench)
    monkeypatch.setattr(ide_private, "loader_for", lambda editor: None)
    shown = bench.press("show", yes=True, name="T1", file=path)
    assert not shown["ok"] and ide_private.EDITOR_VIEW in shown["error"]


# --- logged in -----------------------------------------------------------------

def test_apply_of_a_new_trace_while_logged_in_says_why_it_cannot(bench):
    bench.online = True
    refused = bench.press("apply", yes=True, name="T1", job=definition())
    assert not refused["ok"]
    assert "logged in" in refused["error"]
    assert bench.trace_named("T1") is None


def test_apply_to_an_existing_trace_while_logged_in_works(bench):
    bench.press("apply", yes=True, name="T1", job=definition("a.x"))
    bench.online = True
    again = bench.press("apply", yes=True, name="T1", job=definition("a.y"))
    assert again["ok"], again["error"]


def test_show_into_an_existing_trace_while_logged_in_works(bench):
    path = saved_trace(bench)
    bench.online = True
    shown = bench.press("show", yes=True, name="T1", file=path)
    assert shown["ok"], shown["error"]


def test_save_of_a_file_it_cannot_read_says_so(monkeypatch, tmp_path):
    bench = Bench(monkeypatch, csv_text=u"garbage line without separator")
    bench.press("apply", yes=True, name="T1", job=definition())
    saved = bench.press("save", name="T1", out=str(tmp_path / "run"))
    assert "could not be read" in saved["data"]["why"]
    assert "holds no samples" not in saved["data"]["why"]


def test_job_of_a_trigger_with_no_numeric_level_is_unusable(bench):
    bench.press("apply", yes=True, name="T1", job=definition(
        trigger={"variable": "PLC_PRG.n", "edge": "rising", "level": 1,
                 "post_samples": 5}))
    bench.trace_named("T1").trigger_level = True
    read = bench.press("job", name="T1")
    assert read["ok"], read["error"]
    assert read["data"]["usable"].startswith("no")
