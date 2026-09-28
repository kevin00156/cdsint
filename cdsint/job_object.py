# -*- coding: utf-8 -*-
"""Tie the IDE a headless run starts to the life of the cdsint that started it.

Windows only, through ctypes; everywhere else there is nothing to do, since
no IDE runs there. What it can only show on a real machine: kill cdsint from
Task Manager mid-run and the --noUI IDE goes with it.

The IDE joins the job once Popen has returned, so a cdsint killed in the
moment between the two leaves it running. Popen cannot start a process
suspended, and the moment is too short to be worth giving up Popen for.
"""
from __future__ import print_function

import ctypes
import os

WINDOWS = os.name == "nt"

JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK = 0x1000
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000


class _BasicLimits(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", ctypes.c_uint32),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", ctypes.c_uint32),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", ctypes.c_uint32),
                ("SchedulingClass", ctypes.c_uint32)]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BasicLimits),
                ("IoInfo", ctypes.c_ulonglong * 6),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


def die_with_us(child):
    """Make Windows kill child when this process ends, however it ends.

    The launcher kills the IDE it started on a timeout and on Ctrl-C, but a
    launcher that is itself killed outright runs no code at all, and left a
    --noUI IDE with no window holding the project's lock. A job object with
    KILL_ON_JOB_CLOSE is closed by Windows along with our last handle to it.
    SILENT_BREAKAWAY_OK leaves whatever the IDE starts out of the job, so
    only the IDE goes with us.

    Returns the job's handle, which must stay open for as long as we run,
    or None where there is no such thing or Windows said no. The caller
    says so, because then the old way out is the only one.
    """
    if not WINDOWS:
        return None
    kernel = _kernel32()
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        return None
    limits = _ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = (
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        | JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK)
    if kernel.SetInformationJobObject(
            job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(limits),
            ctypes.sizeof(limits)) and \
            kernel.AssignProcessToJobObject(job, int(child._handle)):
        return job
    kernel.CloseHandle(job)
    return None


def _kernel32():
    """kernel32 with the signatures spelled out.

    Left to its defaults ctypes returns a HANDLE as a C int, and a 64-bit
    handle cut to 32 bits is somebody else's handle.
    """
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    handle, pointer = ctypes.c_void_p, ctypes.c_void_p
    kernel.CreateJobObjectW.restype = handle
    kernel.CreateJobObjectW.argtypes = [pointer, ctypes.c_wchar_p]
    kernel.SetInformationJobObject.argtypes = [handle, ctypes.c_int,
                                               pointer, ctypes.c_uint32]
    kernel.AssignProcessToJobObject.argtypes = [handle, handle]
    kernel.CloseHandle.argtypes = [handle]
    return kernel
