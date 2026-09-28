# -*- coding: utf-8 -*-
"""Tests for cdsint/process.py: is that pid still the process that wrote it.

The Windows half is driven through a fake kernel32, because CI is Linux.
What that cannot show is that the real signatures are right; that needs a
Windows machine (a live IDE's pid, then the same pid after it is closed).
"""
import os
import subprocess
import sys

import pytest

from cdsint import process

FILETIME_OF = process._EPOCH_DIFFERENCE_S  # epoch 0, in FILETIME seconds


class FakeKernel(object):
    """Just enough of kernel32 to answer about one process."""

    def __init__(self, opens=True, exit_code=process.STILL_ACTIVE,
                 created=1000.0):
        self.opens = opens
        self.exit_code = exit_code
        self.created = created
        self.closed = []

    def OpenProcess(self, access, inherit, pid):
        assert access == process.PROCESS_QUERY_LIMITED_INFORMATION
        return 77 if self.opens else 0

    def GetExitCodeProcess(self, handle, code):
        code._obj.value = self.exit_code
        return 1

    def GetProcessTimes(self, handle, created, exited, kernel, user):
        created._obj.value = int((self.created + FILETIME_OF) * 1e7)
        return 1

    def CloseHandle(self, handle):
        self.closed.append(handle)
        return 1


@pytest.fixture
def windows(monkeypatch):
    def use(kernel, last_error=0):
        monkeypatch.setattr(process, "WINDOWS", True)
        monkeypatch.setattr(process, "_kernel32", lambda: kernel)
        monkeypatch.setattr(process, "_last_error", lambda: last_error)
        return kernel
    return use


def test_a_process_still_active_is_running(windows):
    kernel = windows(FakeKernel())
    assert process.running(1234) is True
    assert kernel.closed == [77]


def test_a_process_that_exited_is_not_running(windows):
    windows(FakeKernel(exit_code=0))
    assert process.running(1234) is False


def test_no_such_pid_is_not_running(windows):
    windows(FakeKernel(opens=False), last_error=process.ERROR_INVALID_PARAMETER)
    assert process.running(1234) is False


def test_a_process_we_may_not_open_is_still_there(windows):
    windows(FakeKernel(opens=False), last_error=process.ERROR_ACCESS_DENIED)
    assert process.running(1234) is True


def test_a_pid_handed_to_a_newer_process_is_not_the_one_recorded(windows):
    # The IDE crashed, Windows gave its pid to something started later, and
    # the registration's pid now names a process that never wrote it.
    windows(FakeKernel(created=5000.0))
    assert process.running(1234, not_after=1000.0) is False
    assert process.running(1234, not_after=6000.0) is True


def test_no_pid_cannot_be_told(windows):
    windows(FakeKernel())
    assert process.running(None) is None


def test_a_registration_is_asked_with_its_start_time(windows):
    windows(FakeKernel(created=5000.0))
    assert process.registration_running(
        {"pid": 1234, "started_at_epoch": 1000.0}) is False


@pytest.mark.skipif(os.name == "nt", reason="the POSIX probe")
def test_posix_sees_this_process_and_not_a_reaped_one(monkeypatch):
    monkeypatch.setattr(process, "WINDOWS", False)
    assert process.running(os.getpid()) is True
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    assert process.running(child.pid) is False
