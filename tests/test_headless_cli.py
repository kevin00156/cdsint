# -*- coding: utf-8 -*-
"""What the CLI decides to launch, and the command line it builds.

Everything up to the moment the IDE process starts: which install answers
to the name, whether the project is already open, how the profile and the
job reach a process that cannot be handed an argument list. What it makes
of what came back is test_headless_result.py.
"""
import os

import pytest

from cds.core import ipc, trace_job
from cds.ide import headless as ide_side
from cdsint import headless as cli_side
from cds.core.exits import EXIT_HEADLESS
from cdsint.exits import Failure
from tests.headless_fakes import (   # noqa: F401  fixtures
    FakeProcess, OK_REPORT, launching, leaves_a_lock, machine, make,
    written_report)


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


def test_an_install_without_the_tree_is_refused_before_any_ide_starts(
        machine, monkeypatch):
    # `pip install .` without -e, or from a git URL, lands cds/, cdsint/ and
    # engine/ under site-packages and nothing else. The IDE side then dies
    # inside the IDE on the missing profile, which reads as an IDE bug; the
    # CLI can say what is wrong before spending an IDE launch on it.
    (machine / "line.project").write_text("binary", encoding="utf-8")
    monkeypatch.setattr(cli_side, "INSTALL_ROOT_MARKER",
                        str(machine / "profiles" / "default.json"))
    with pytest.raises(Failure) as raised:
        cli_side.Headless(str(machine / "line.project"), "3.5.21.40")
    assert raised.value.code == EXIT_HEADLESS
    assert "pip install -e" in str(raised.value)
    assert str(machine / "profiles" / "default.json") in str(raised.value)


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


# --- the deadline --------------------------------------------------------

def test_a_trace_step_waits_its_duration_on_top_of_the_timeout(machine,
                                                               monkeypatch):
    # --timeout bounds the trace's own work; the recording itself is time the
    # caller asked for, so a ten-minute trace must not be killed at two
    # (SPEC 6.8).
    launches = launching(monkeypatch)
    written_report(monkeypatch, OK_REPORT)
    started = make(machine, monkeypatch)
    job, _problem = trace_job.normalise(
        {"task": "MainTask", "variables": ["PRG_X.var"], "duration_s": 600,
         "out": "run1"})
    plain = started.deadline([("plc connect", {"job": None})])
    assert started.deadline([("plc trace", {"job": job})]) == plain + 600
    started.run([("plc trace", {"job": job})])
    assert launches[0]["process"].waited == plain + 600


def test_every_other_step_keeps_the_timeout_it_had(machine, monkeypatch):
    started = make(machine, monkeypatch)
    one = started.deadline([("export", {})])
    assert started.deadline([("import", {}), ("export", {})]) == \
        one + started.timeout
