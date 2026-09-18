# -*- coding: utf-8 -*-
"""What the CLI makes of what came back.

The exit code it did or did not get, the marks that say stdout reached it,
the report it must not read from the run before, the deadline, and what a
kill leaves behind. Deciding what to launch is test_headless_cli.py.
"""
import os

import pytest

from cds.core import ipc
from cds.ide import headless as ide_side
from cdsint import headless as cli_side
from cdsint import report as report_side
from cds.core.exits import EXIT_HEADLESS, EXIT_TIMEOUT
from cdsint.exits import Failure
from tests.headless_fakes import (   # noqa: F401  fixtures
    FakeProcess, OK_REPORT, launching, leaves_a_lock, machine, make,
    written_report)


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
    # Real project names look like "包裝機 v2.project", and the report file
    # is named after them.
    made = report_side.default_report(u"C:\\p\\包裝機 v2.project")
    assert made.endswith(".json") and " " not in os.path.basename(made)
    assert os.path.basename(made).encode("ascii")

def test_the_report_names_the_folder_the_engine_read(machine, monkeypatch):
    # The CLI used to write its own flag into this field, so the report said
    # --sync-dir whichever folder the engine had actually read. The IDE side
    # is the only one that knows, so the report is where the answer comes
    # from (SPEC 4.2).
    launching(monkeypatch, code=0)
    written_report(monkeypatch, dict(OK_REPORT, sync_dir=r"D:\what-ran"))
    started = make(machine, monkeypatch, sync_dir=r"D:\what-was-asked")

    started.run([("export", {})])

    assert ipc.read_json(started.report_path)["sync_dir"] == r"D:\what-ran"
