# -*- coding: utf-8 -*-
"""Whether a process id still names the process that wrote it down.

The registrations under the instances root and cdsint's own launch lock both
carry a pid, and both outlive the process when it is killed or crashes. A
record like that is only evidence while its process runs, so this is the
question the readers ask before they trust one.

Windows asks through ctypes: OpenProcess, then GetExitCodeProcess for
STILL_ACTIVE. NOT os.kill(pid, 0), which on Windows CPython terminates the
process it was meant to probe. Elsewhere, where only CI runs, os.kill with
signal 0 is the probe it looks like.

Pid reuse: Windows hands a freed pid out again. Given the moment the record
was written, a process created after it is some other program that got the
same number, and the record is dead. POSIX has no cheap creation time, so
there a reused pid reads as alive; nothing but CI runs there.

CPython only (PRINCIPLES.md 8): cds/core takes the answer as a function, so
it stays pure.
"""
from __future__ import print_function

import ctypes
import os

WINDOWS = os.name == "nt"

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
ERROR_ACCESS_DENIED = 5
ERROR_INVALID_PARAMETER = 87

# FILETIME counts 100 ns ticks from 1601; this many seconds lie between that
# and the Unix epoch.
_EPOCH_DIFFERENCE_S = 11644473600
# A process created after a registration's stamp is a newcomer on a reused
# pid. The two times come from different clocks -- the kernel's record of
# when the process was created, and time.time() when the watcher stamped --
# so a creation this far past the stamp is still taken for the same process.
CLOCK_SLACK_S = 2.0


def running(pid, not_after=None):
    """True, False, or None when this machine cannot tell.

    not_after is the epoch at which the process was known to exist, when
    the caller has one: a process created later is a reused pid.
    """
    if not pid:
        return None
    if WINDOWS:
        return _running_windows(int(pid), not_after)
    return _running_posix(int(pid))


def registration_running(reg):
    """running() for one watcher's registration, as cds/core wants it."""
    return running(reg.get("pid"), reg.get("started_at_epoch"))


def _running_posix(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True     # somebody else's, and there
    return True


def _running_windows(pid, not_after):
    kernel = _kernel32()
    handle = kernel.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return _why_not_opened(_last_error())
    try:
        code = ctypes.c_uint32()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
            return None
        # A process that exited with 259 reads as running: the API's own
        # ambiguity, and no IDE exits with it.
        if code.value != STILL_ACTIVE:
            return False
        created = _created_epoch(kernel, handle)
        if not_after is None or created is None:
            return True
        return created <= float(not_after) + CLOCK_SLACK_S
    finally:
        kernel.CloseHandle(handle)


def _why_not_opened(error):
    """OpenProcess said no: which no."""
    if error == ERROR_INVALID_PARAMETER:
        return False    # no such process
    if error == ERROR_ACCESS_DENIED:
        return True     # there, and not ours to look at
    return None


def _created_epoch(kernel, handle):
    """When the process began, as Unix epoch seconds, or None."""
    times = [ctypes.c_ulonglong() for _ in range(4)]
    if not kernel.GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
        return None
    return times[0].value / 1e7 - _EPOCH_DIFFERENCE_S


def _kernel32():
    """kernel32 with the signatures spelled out.

    Left to its defaults ctypes returns a HANDLE as a C int, and a 64-bit
    handle cut to 32 bits is somebody else's handle.
    """
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    handle, dword, pointer = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p
    kernel.OpenProcess.restype = handle
    kernel.OpenProcess.argtypes = [dword, ctypes.c_int, dword]
    kernel.GetExitCodeProcess.argtypes = [handle, pointer]
    kernel.GetProcessTimes.argtypes = [handle] + [pointer] * 4
    kernel.CloseHandle.argtypes = [handle]
    return kernel


def _last_error():
    return ctypes.get_last_error()
