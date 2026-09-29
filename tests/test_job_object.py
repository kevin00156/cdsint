# -*- coding: utf-8 -*-
"""Tests for cdsint/job_object.py: the headless IDE dies with its cdsint.

Driven through a fake kernel32, because CI is Linux. What this cannot show
is that Windows really kills the IDE when cdsint is killed outright; that
takes a Windows machine and Task Manager.
"""
import ctypes

import pytest

from cdsint import job_object


@pytest.fixture
def windows(monkeypatch):
    def use(kernel):
        monkeypatch.setattr(job_object, "WINDOWS", True)
        monkeypatch.setattr(job_object, "_kernel32", lambda: kernel)
        return kernel
    return use


class JobKernel(object):
    """kernel32's job object calls, recording what they were asked."""

    def __init__(self, assigns=True):
        self.assigns = assigns
        self.limits = None
        self.assigned = None
        self.closed = []

    def CreateJobObjectW(self, attributes, name):
        return 55

    def SetInformationJobObject(self, job, kind, info, size):
        assert kind == job_object.JOB_OBJECT_EXTENDED_LIMIT_INFORMATION
        assert size == ctypes.sizeof(job_object._ExtendedLimits)
        self.limits = info._obj.BasicLimitInformation.LimitFlags
        return 1

    def AssignProcessToJobObject(self, job, child):
        self.assigned = child
        return 1 if self.assigns else 0

    def CloseHandle(self, handle):
        self.closed.append(handle)
        return 1


class Child(object):
    _handle = 1234


def test_the_ide_is_put_in_a_job_that_dies_with_us(windows):
    kernel = windows(JobKernel())
    assert job_object.die_with_us(Child()) == 55
    assert kernel.limits & job_object.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    # Only the IDE: what it starts itself stays out of the job.
    assert kernel.limits & job_object.JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK
    assert kernel.assigned == 1234 and kernel.closed == []


def test_a_job_windows_will_not_take_the_ide_into_is_closed(windows):
    kernel = windows(JobKernel(assigns=False))
    assert job_object.die_with_us(Child()) is None
    assert kernel.closed == [55]


def test_there_is_no_job_off_windows(monkeypatch):
    monkeypatch.setattr(job_object, "WINDOWS", False)
    assert job_object.die_with_us(Child()) is None


def test_the_limits_structure_has_the_size_windows_expects():
    # JOBOBJECT_EXTENDED_LIMIT_INFORMATION: 144 bytes on 64-bit Windows.
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        assert ctypes.sizeof(job_object._ExtendedLimits) == 144
