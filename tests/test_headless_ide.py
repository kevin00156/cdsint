# -*- coding: utf-8 -*-
"""The IDE half of the headless form: what the script does once it is inside.

Runs under CPython with fake CODESYS globals, the same way the watcher tests
do. What it cannot show is whether a real IDE starts — that is the
acceptance run's job, and the CLI half is in test_headless_cli.py.
"""
import os
import time

import pytest

from cds.core import ipc
from cds.ide import entries
from cds.ide import headless as ide_side
from tests.fakes import DeafSystem, make_globals



# --- fake CODESYS globals --------------------------------------------------

class FakeFlags(object):
    """Enum members that or together into something comparable."""

    def __init__(self, name):
        self.name = name

    def __or__(self, other):
        return FakeFlags(self.name + "|" + other.name)


class FakePromptHandling(object):
    LogMessageKeys = FakeFlags("LogMessageKeys")
    LogSimplePrompts = FakeFlags("LogSimplePrompts")
    ProcessScriptPrompts = FakeFlags("ProcessScriptPrompts")


class FakePromptResult(object):
    Yes = "PromptResult.Yes"
    No = "PromptResult.No"


class PromptSystem(DeafSystem):
    def __init__(self):
        self.prompt_handling = None
        self.prompt_answers = {}


class OpeningProjects(object):
    """A `projects` that opens whatever it is told to, or refuses to."""

    def __init__(self, opens=True):
        self.primary = None
        self.opened = []
        self._opens = opens

    def open(self, path):
        self.opened.append(path)
        if self._opens:
            self.primary = make_globals(path)["projects"].primary
        return self.primary


@pytest.fixture
def ide():
    return {"system": PromptSystem(), "projects": OpeningProjects(),
            "PromptHandling": FakePromptHandling,
            "PromptResult": FakePromptResult}


def job(tmp_path, **extra):
    record = {"project": str(tmp_path / "line.project"),
              "report": str(tmp_path / "r.json"), "commands": [], "answers": {},
              "sync_dir": None}
    record.update(extra)
    return record


def one_step(command="export", ok=True, **data):
    """Stand in for entries.run without touching the engine."""
    from cds.ide import silent

    def run(ide_globals, name, args):
        return silent.Outcome([], "", result={"ok": ok, "summary": name,
                                              "data": data})
    return run


# --- the IDE half ----------------------------------------------------------

def test_the_prompt_keys_are_logged_so_an_unanswered_one_is_visible(ide):
    # Without LogMessageKeys a prompt with no answer just cancels whatever it
    # was blocking, and the report says nothing about why (SPEC 6.4).
    ide_side.answer_prompts(ide, {})
    assert "LogMessageKeys" in ide["system"].prompt_handling.name


def test_nothing_is_answered_unless_the_caller_said_so(ide):
    # The upgrade prompt rewrites the project's storage format, and after
    # that the IDE it came from cannot open it again.
    ide_side.answer_prompts(ide, {})
    assert ide["system"].prompt_answers == {}


def test_an_answer_reaches_the_prompt_table(ide):
    ide_side.answer_prompts(ide, {"UpgradeProjectConfirmation": "Yes"})
    assert ide["system"].prompt_answers == {
        "UpgradeProjectConfirmation": "PromptResult.Yes"}


def test_a_project_that_will_not_open_names_the_likely_prompt(ide, tmp_path):
    ide["projects"] = OpeningProjects(opens=False)
    report = ide_side.run_job(ide, job(tmp_path))
    assert report["opened"] is False
    assert "UpgradeProjectConfirmation" in report["error"]
    assert report["intended_exit"] == ide_side.EXIT_FAILED


def test_every_command_runs_and_each_gets_its_own_record(ide, tmp_path,
                                                         monkeypatch):
    monkeypatch.setattr(entries, "run", one_step())
    report = ide_side.run_job(ide, job(tmp_path, commands=[
        {"command": "import", "args": {"yes": True}},
        {"command": "export", "args": {}}]))
    assert [r["command"] for r in report["results"]] == ["import", "export"]
    assert report["intended_exit"] == ide_side.EXIT_OK


def test_a_step_reports_how_long_it_actually_took(ide, tmp_path, monkeypatch):
    # entries.answer used to take started=None from here, and new_result then
    # read "now" for both ends: a forty-second import printed as 0.0s and the
    # --json record's started_at was the moment it finished.
    def slow(ide_globals, name, args):
        from cds.ide import silent
        time.sleep(0.2)
        return silent.Outcome([], "", result={"ok": True, "summary": name,
                                              "data": {}})
    monkeypatch.setattr(entries, "run", slow)

    report = ide_side.run_job(ide, job(tmp_path, commands=[
        {"command": "export", "args": {}}]))

    # elapsed_s, not the timestamps: those are ISO strings to the second, so
    # a fifth of a second does not show in them either way.
    assert report["results"][0]["elapsed_s"] >= 0.2


def test_a_failed_step_stops_the_ones_after_it(ide, tmp_path, monkeypatch):
    # Exporting after a half-finished import would write that half out and
    # call the round trip clean.
    monkeypatch.setattr(entries, "run", one_step(ok=False))
    report = ide_side.run_job(ide, job(tmp_path, commands=[
        {"command": "import", "args": {}}, {"command": "export", "args": {}}]))
    assert [r["command"] for r in report["results"]] == ["import"]
    assert report["intended_exit"] == ide_side.EXIT_FAILED


def test_the_sync_folder_reaches_every_command_as_an_argument(ide, tmp_path,
                                                              monkeypatch):
    # It is an override the engine reads, not something written into the
    # project (SPEC 4.2), so it travels the way -y does: in each command's
    # own arguments, which cds/ide/silent.py puts in the body's namespace.
    seen = []
    step = one_step()

    def record(ide_globals, name, args):
        seen.append(args)
        return step(ide_globals, name, args)

    monkeypatch.setattr(entries, "run", record)
    ide_side.run_job(ide, job(tmp_path, sync_dir="D:" + os.sep + "sync",
                              commands=[{"command": "import", "args": {"yes": True}},
                                        {"command": "export", "args": {}}]))

    assert [a["sync_dir"] for a in seen] == ["D:" + os.sep + "sync"] * 2
    assert seen[0]["yes"] is True     # the step's own flags are still there


def test_no_sync_dir_leaves_the_commands_to_read_the_settings_file(ide,
                                                                   tmp_path,
                                                                   monkeypatch):
    seen = []
    step = one_step()

    def record(ide_globals, name, args):
        seen.append(args)
        return step(ide_globals, name, args)

    monkeypatch.setattr(entries, "run", record)
    ide_side.run_job(ide, job(tmp_path,
                              commands=[{"command": "export", "args": {}}]))

    assert "sync_dir" not in seen[0]



def test_the_report_is_written_where_the_job_asked(ide, tmp_path, monkeypatch):
    monkeypatch.setattr(entries, "run", one_step())
    record = job(tmp_path, commands=[{"command": "export", "args": {}}])
    path = str(tmp_path / "job.json")
    ipc.write_json(path, record)
    assert ide_side.main(ide, path) == ide_side.EXIT_OK
    assert ipc.read_json(record["report"])["opened"] is True


# --- the CLI half ----------------------------------------------------------

def test_an_open_that_throws_gets_the_same_hint_as_one_that_returns_nothing(
        ide, tmp_path, monkeypatch):
    # Cancelling the upgrade prompt shows up both ways: open() returning
    # nothing, and it throwing "Do not upgrade the older version project".
    def refuse(path):
        raise RuntimeError("Do not upgrade the older version project")
    ide["projects"].open = refuse
    report = ide_side.run_job(ide, job(tmp_path))
    assert report["opened"] is False
    assert "--answer KEY=VALUE" in report["error"]
    assert "Do not upgrade" in report["error"]
