# -*- coding: utf-8 -*-
"""One machine, one fake IDE process, and the report it did or did not write.

Shared by the two halves of the CLI-side headless tests: what it decides to
launch (test_headless_cli.py) and what it makes of what came back
(test_headless_result.py). Popen is faked because the thing under test is
the decision and the reading, not whether a real IDE starts.

Not a conftest.py: a fixture named `machine` that replaces installs.find()
has no business being visible to every other test in the directory.
"""
import subprocess

import pytest

from cds.core import ipc
from cdsint import headless as cli_side
from cdsint import installs





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
