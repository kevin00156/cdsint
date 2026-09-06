# -*- coding: utf-8 -*-
"""Tests for both halves of the headless form.

The IDE half runs under CPython with fake CODESYS globals, the same way the
watcher tests do. The CLI half gets a fake Popen, because the thing being
checked is what it decides to launch and what it makes of what came back —
not whether a real IDE starts, which is the acceptance run's job.
"""
import json
import os
import subprocess
import time

import pytest

from cds.core import ipc
from cds.ide import entries
from cds.ide import headless as ide_side
from cdsint import headless as cli_side
from cdsint import installs
from cdsint import report as report_side
from cds.core.exits import EXIT_HEADLESS, EXIT_TIMEOUT
from cdsint.exits import Failure
from tests.test_watcher import FakeSystem, make_globals


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


class PromptSystem(FakeSystem):
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



def test_the_report_names_the_folder_the_engine_read(machine, monkeypatch):
    # The CLI used to write its own flag into this field, so the report said
    # --sync-dir whichever folder the engine had actually read. The IDE side
    # is the only one that knows, so the report is where the answer comes
    # from (SPEC 4.2).
    launching(monkeypatch, code=0)
    written_report(monkeypatch, dict(OK_REPORT, sync_dir="D:\what-ran"))
    started = make(machine, monkeypatch, sync_dir="D:\what-was-asked")

    started.run([("export", {})])

    assert ipc.read_json(started.report_path)["sync_dir"] == "D:\what-ran"


def test_the_report_is_written_where_the_job_asked(ide, tmp_path, monkeypatch):
    monkeypatch.setattr(entries, "run", one_step())
    record = job(tmp_path, commands=[{"command": "export", "args": {}}])
    path = str(tmp_path / "job.json")
    ipc.write_json(path, record)
    assert ide_side.main(ide, path) == ide_side.EXIT_OK
    assert ipc.read_json(record["report"])["opened"] is True


# --- the CLI half ----------------------------------------------------------

@pytest.fixture
def machine(tmp_path, monkeypatch):
    """One install, so resolve() has something to find."""
    fake = [{"name": "CODESYS 3.5.21.40", "exe": r"C:\ide\CODESYS.exe",
             "profiles": ["CODESYS V3.5 SP21 Patch 4"],
             "script_dir": r"C:\ScriptDir", "script_dir_needs_admin": False,
             "run_as_admin": None}]
    monkeypatch.setattr(installs, "find", lambda: fake)
    return tmp_path


class FakeProcess(object):
    """Popen's stand-in: writes the report the IDE would have written."""

    def __init__(self, launches, code=0, report=None, stdout=None, dies=True):
        self.launches = launches
        self._code = code
        self._report = report
        self._stdout = stdout
        self._dies = dies
        self.pid = 4321
        self.killed = False
        self.waited = None

    def wait(self, timeout=None):
        """A process that never exits on its own, until it is killed.

        The second wait is the one after kill(), and what it answers decides
        whether the lock file may be cleared, so it is modelled rather than
        assumed: `dies=False` is the process that survives its own kill.
        """
        if self.killed and self._dies:
            return -1
        if self._code is None or self.killed:
            raise subprocess.TimeoutExpired("cmd", timeout)
        self.waited = timeout
        return self._code

    def kill(self):
        self.killed = True


def launching(monkeypatch, code=0, dies=True):
    """Replace Popen and record what it was asked to start."""
    launches = []

    def popen(command, stdout=None, stderr=None, env=None, **kwargs):
        launches.append({"command": command, "env": env})
        launches[-1]["process"] = FakeProcess(launches, code, dies=dies)
        return launches[-1]["process"]

    monkeypatch.setattr(subprocess, "Popen", popen)
    return launches


def written_report(monkeypatch, report):
    """Make the fake launch drop `report` where the CLI will look for it."""
    real = cli_side.Headless._launch

    def launch(self, job_path, deadline):
        if report is not None:
            ipc.write_json(self.report_path, report)
        return real(self, job_path, deadline)
    monkeypatch.setattr(cli_side.Headless, "_launch", launch)


def leaves_a_lock(monkeypatch):
    """Make the fake launch leave the lock file a real IDE leaves behind."""
    real = cli_side.Headless._launch

    def launch(self, job_path, deadline):
        open(self.project + ".~u", "w").close()
        return real(self, job_path, deadline)
    monkeypatch.setattr(cli_side.Headless, "_launch", launch)


def make(machine, monkeypatch, project="line.project", **kwargs):
    path = machine / project
    path.write_text("binary", encoding="utf-8")
    kwargs.setdefault("install", "3.5.21.40")
    kwargs.setdefault("report", str(machine / "r.json"))
    return cli_side.Headless(str(path), **kwargs)


OK_REPORT = {"opened": True, "intended_exit": 0, "ide": "CODESYS.exe",
             "results": [{"ok": True, "command": "export", "data": {}}]}


# --- refusing before the launch --------------------------------------------

@pytest.mark.parametrize("lock", ["line.project.~u", "line.~u"])
def test_a_locked_project_is_refused_with_the_lock_path(machine, lock):
    # Both filename shapes exist in the wild; checking one leaves the gate
    # blind half the time (SPEC 6.4).
    (machine / "line.project").write_text("binary", encoding="utf-8")
    (machine / lock).write_text("", encoding="utf-8")
    with pytest.raises(Failure) as raised:
        cli_side.Headless(str(machine / "line.project"), "3.5.21.40")
    assert raised.value.code == EXIT_HEADLESS and lock in str(raised.value)


def test_force_lock_goes_ahead_anyway(machine):
    (machine / "line.project").write_text("binary", encoding="utf-8")
    (machine / "line.project.~u").write_text("", encoding="utf-8")
    started = cli_side.Headless(str(machine / "line.project"), "3.5.21.40",
                                force_lock=True)
    assert started.project.endswith("line.project")


def test_a_project_that_is_not_there_is_refused(machine):
    with pytest.raises(Failure) as raised:
        cli_side.Headless(str(machine / "nope.project"), "3.5.21.40")
    assert raised.value.code == EXIT_HEADLESS


def test_the_install_has_to_be_named(machine):
    (machine / "line.project").write_text("binary", encoding="utf-8")
    with pytest.raises(Failure) as raised:
        cli_side.Headless(str(machine / "line.project"))
    assert raised.value.code == EXIT_HEADLESS


# --- the launch ------------------------------------------------------------

def test_the_profile_is_quoted_on_one_command_line(machine, monkeypatch):
    launches = launching(monkeypatch)
    written_report(monkeypatch, OK_REPORT)
    make(machine, monkeypatch).run([("export", {})])
    command = launches[0]["command"]
    assert isinstance(command, str)
    assert '--profile="CODESYS V3.5 SP21 Patch 4"' in command
    assert "--noUI" in command and "--runscript=" in command


def test_the_job_goes_through_the_environment_not_the_command_line(machine,
                                                                   monkeypatch):
    # --scriptargs is one string split on spaces, and these project paths
    # have spaces and Chinese in them (SPEC 6.4).
    launches = launching(monkeypatch)
    written_report(monkeypatch, OK_REPORT)
    started = make(machine, monkeypatch)
    started.run([("export", {"delete_orphans": True})])
    job_path = launches[0]["env"][ide_side.JOB_ENV]
    assert "--scriptargs" not in launches[0]["command"]
    sent = ipc.read_json(job_path)
    assert sent["project"] == started.project
    assert sent["commands"] == [{"command": "export",
                                 "args": {"delete_orphans": True}}]


def test_one_launch_serves_every_step(machine, monkeypatch):
    # Starting an IDE and opening a project costs half a minute, and verify
    # is four commands.
    launches = launching(monkeypatch)
    written_report(monkeypatch, OK_REPORT)
    make(machine, monkeypatch).run([("import", {}), ("export", {})])
    assert len(launches) == 1


# --- reading what came back ------------------------------------------------

def test_the_sync_folder_is_resolved_before_anyone_is_told_about_it(machine,
                                                                    monkeypatch):
    # The IDE side hands this string to every command as its sync folder, and
    # the IDE's working directory is not the shell's, so a relative path would
    # land somewhere neither of them meant.
    started = make(machine, monkeypatch, sync_dir="exported")
    assert os.path.isabs(started.sync_dir())
    assert started.sync_dir().endswith("exported")


def test_the_report_says_which_folder_the_run_used(machine, monkeypatch):
    launching(monkeypatch)
    written_report(monkeypatch, OK_REPORT)
    started = make(machine, monkeypatch, sync_dir=str(machine / "exported"))
    results = started.run([("export", {})])
    assert ipc.read_json(started.report_path)["sync_dir"] == started.sync_dir()
    # And in the record, next to the other two facts only this form knows.
    assert results[0]["sync_dir"] == started.sync_dir()


def test_each_result_says_which_ide_ran_it(machine, monkeypatch):
    launching(monkeypatch)
    written_report(monkeypatch, OK_REPORT)
    started = make(machine, monkeypatch)
    results = started.run([("export", {})])
    assert results[0]["ide"] == "CODESYS.exe"
    assert results[0]["report_path"] == started.report_path


def test_a_disagreeing_exit_code_is_recorded_and_said_out_loud(machine,
                                                               monkeypatch,
                                                               capsys):
    # Whether the exit code can be used as a gate is a fact to measure.
    launching(monkeypatch, code=7)
    written_report(monkeypatch, OK_REPORT)
    started = make(machine, monkeypatch)
    started.run([("export", {})])
    assert ipc.read_json(started.report_path)["exit_code_trusted"] is False
    # Kept as a note rather than printed here: cdsint/report.py decides where
    # a sentence goes, and under --json this belongs in the record.
    assert any("cannot be used as a gate" in note for note in started.notes)


def test_a_matching_exit_code_is_trusted(machine, monkeypatch):
    launching(monkeypatch, code=0)
    written_report(monkeypatch, OK_REPORT)
    started = make(machine, monkeypatch)
    started.run([("export", {})])
    assert ipc.read_json(started.report_path)["exit_code_trusted"] is True


def test_stdout_counts_as_reached_only_with_both_marks(machine, monkeypatch):
    # Half the output is not the output: seeing only BEGIN means the script
    # died partway, which is not "stdout works".
    launching(monkeypatch)
    written_report(monkeypatch, OK_REPORT)
    started = make(machine, monkeypatch)
    started.run([("export", {})])
    with open(started.stdout_path(), "w", encoding="utf-8") as handle:
        handle.write(ide_side.BEGIN_MARK)
    assert started._stdout_reached() is False
    with open(started.stdout_path(), "w", encoding="utf-8") as handle:
        handle.write(ide_side.BEGIN_MARK + "\nwork\n" + ide_side.END_MARK)
    assert started._stdout_reached() is True


def test_the_wait_covers_every_step_not_just_one(machine, monkeypatch):
    # --timeout bounds a step in both forms (SPEC 4.2). A verify is four of
    # them plus a launch, and the default used to kill the flagship command
    # at 121s with all four steps already reported ok.
    launches = launching(monkeypatch)
    written_report(monkeypatch, OK_REPORT)
    started = make(machine, monkeypatch, timeout=30)
    started.run([("import", {}), ("export", {}), ("compare", {}),
                 ("build", {})])
    assert launches[0]["process"].waited == (
        cli_side.STARTUP_GRACE_S + 4 * 30 + cli_side.SHUTDOWN_GRACE_S)


def test_a_kill_after_the_script_finished_is_not_a_failed_run(machine,
                                                              monkeypatch,
                                                              capsys):
    # A complete report is evidence of what happened; a slow exit afterwards
    # says nothing about the work and must not overturn it (SPEC 6.4).
    launching(monkeypatch, code=None)
    written_report(monkeypatch, OK_REPORT)
    started = make(machine, monkeypatch, timeout=0.01)
    results = started.run([("export", {})])
    assert results[0]["ok"] is True
    saved = ipc.read_json(started.report_path)
    assert saved["timed_out"] is True
    assert "did not exit" in saved["error"] and "dialog" not in saved["error"]
    # Said once. It used to be printed here and again by cdsint/exits.py when
    # the Failure carrying the same sentence was reported.
    assert started.notes.count(saved["error"]) == 1
    assert results[0]["notes"] == started.notes


def test_the_lock_our_own_killed_ide_left_behind_is_cleared(machine,
                                                            monkeypatch,
                                                            capsys):
    # cdsint made this lock and knows it, so asking the caller for
    # --force-lock on the next run would be asking them to confirm our mess.
    launching(monkeypatch, code=None)
    leaves_a_lock(monkeypatch)
    started = make(machine, monkeypatch, timeout=0.01)
    with pytest.raises(Failure):
        started.run([("export", {})])
    assert not os.path.exists(started.project + ".~u")
    assert any("lock" in note for note in started.notes)


def test_a_lock_that_was_there_before_we_started_is_left_alone(machine,
                                                               monkeypatch,
                                                               capsys):
    # Suggestion 1. --force-lock says "go ahead anyway", not "that lock is
    # mine". If the other IDE really was open, clearing its lock on the way
    # out lets the next run in beside it, and two IDEs writing one .project
    # ends with the later save winning.
    (machine / "line.project").write_text("binary", encoding="utf-8")
    (machine / "line.project.~u").write_text("", encoding="utf-8")
    launching(monkeypatch, code=None)
    started = make(machine, monkeypatch, timeout=0.01, force_lock=True)

    with pytest.raises(Failure):
        started.run([("export", {})])

    assert os.path.exists(started.project + ".~u")
    assert any("was there before" in note for note in started.notes)


def test_a_process_that_survives_its_own_kill_keeps_its_lock(machine,
                                                             monkeypatch):
    # Still running means still possibly writing the project file. A lock
    # cleared now would let the next run open a half-written one.
    launching(monkeypatch, code=None, dies=False)
    leaves_a_lock(monkeypatch)
    started = make(machine, monkeypatch, timeout=0.01)
    with pytest.raises(Failure):
        started.run([("export", {})])
    assert os.path.exists(started.project + ".~u")


def test_ctrl_c_takes_the_ide_it_started_with_it(machine, monkeypatch):
    # Suggestion 10. Without this the --noUI process carries on with no
    # window and nobody watching, holding the project's lock; the next run
    # says exit 4 and prints a lock path, and the person has to go and find
    # the process in Task Manager. cdsint/target.py already un-queues its
    # command on Ctrl-C.
    launches = launching(monkeypatch, code=None)

    def interrupted(self, timeout=None):
        raise KeyboardInterrupt()

    monkeypatch.setattr(FakeProcess, "wait", interrupted)
    with pytest.raises(KeyboardInterrupt):
        make(machine, monkeypatch, timeout=0.01).run([("export", {})])

    assert launches[-1]["process"].killed is True


def test_a_run_that_never_finishes_is_killed_and_blamed_on_a_dialog(machine,
                                                                    monkeypatch):
    launching(monkeypatch, code=None)
    with pytest.raises(Failure) as raised:
        make(machine, monkeypatch, timeout=0.01).run([("export", {})])
    assert raised.value.code == EXIT_TIMEOUT
    assert "dialog" in str(raised.value)


def test_a_killed_run_still_says_what_it_did_to_the_lock_file(machine,
                                                              monkeypatch,
                                                              capsys):
    # There are no results on this path, so the Failure is the only thing the
    # caller ever sees. Without the notes on it, somebody whose lock file we
    # cleared reads a timeout and nothing else.
    launching(monkeypatch, code=None)
    leaves_a_lock(monkeypatch)
    started = make(machine, monkeypatch, timeout=0.01)

    with pytest.raises(Failure) as raised:
        started.run([("export", {})])

    assert raised.value.lines == started.notes
    assert raised.value.report() == EXIT_TIMEOUT
    printed = capsys.readouterr().err
    assert "did not finish" in printed
    assert "removed the lock file" in printed


def test_a_timeout_is_written_into_the_report(machine, monkeypatch):
    launching(monkeypatch, code=None)
    started = make(machine, monkeypatch, timeout=0.01)
    with pytest.raises(Failure):
        started.run([("export", {})])
    saved = ipc.read_json(started.report_path)
    assert saved["exit_code_actual"] is None and saved["pid"] == 4321
    # A caller reading only the report has to find the conclusion there: the
    # exit code it would otherwise reason from is what a kill takes away.
    assert saved["timed_out"] is True and "dialog" in saved["error"]


def test_the_last_run_report_is_not_read_as_this_run_answer(machine,
                                                            monkeypatch):
    # default_report keeps the file on purpose, so the same project's report
    # path already holds the last run when this one starts. An IDE that hangs
    # on a dialog and writes nothing used to leave that file for _collect to
    # read: intended_exit was there, so the run counted as finished, and
    # verify passed on the previous run's numbers.
    started = make(machine, monkeypatch, timeout=0.01)
    ipc.write_json(started.report_path, OK_REPORT)
    launching(monkeypatch, code=None)

    with pytest.raises(Failure) as raised:
        started.run([("import", {"yes": True})])

    assert raised.value.code == EXIT_TIMEOUT


def test_the_last_run_report_is_not_read_after_a_silent_exit(machine,
                                                             monkeypatch):
    # The same hole without a timeout: the IDE exits by itself having written
    # nothing, and the leftover report answers for it.
    started = make(machine, monkeypatch)
    ipc.write_json(started.report_path, OK_REPORT)
    launching(monkeypatch, code=0)

    with pytest.raises(Failure) as raised:
        started.run([("import", {"yes": True})])

    assert raised.value.code == EXIT_HEADLESS


def test_an_ide_that_wrote_no_report_is_a_launch_failure(machine, monkeypatch):
    launching(monkeypatch, code=1)
    with pytest.raises(Failure) as raised:
        make(machine, monkeypatch).run([("export", {})])
    assert raised.value.code == EXIT_HEADLESS


# --- housekeeping ----------------------------------------------------------

def test_stdout_and_the_report_share_a_name_so_two_runs_do_not_collide(machine,
                                                                       monkeypatch):
    started = make(machine, monkeypatch)
    assert started.stdout_path().startswith(started.report_path)
    assert started.stderr_path() != started.stdout_path()


def test_a_report_path_survives_a_project_name_with_spaces_and_chinese(machine):
    # Real project names look like "SheetSplitter v2.project", and the report file
    # is named after them.
    made = report_side.default_report(u"C:\\p\\\u4e09\u660e \u5206\u7d19\u6a5f.project")
    assert made.endswith(".json") and " " not in os.path.basename(made)
    assert os.path.basename(made).encode("ascii")


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
