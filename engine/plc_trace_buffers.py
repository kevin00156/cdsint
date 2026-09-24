# -*- coding: utf-8 -*-
"""Both trace buffers, set through the one private member cdsint depends on.

The script API exposes neither the controller's ring (`uiBufferEntries`) nor
the IDE's per-variable buffer, and with the default ring of 100 a task faster
than about 4 ms loses most of its samples (docs/trace-research.md 2.1). The
trace plug-in's script object has a private `PerformWithWriteableCopy`
that hands a callback the object holding both; this is the only place that
reaches for it, so an IDE release that moves it breaks one file (SPEC 6.8
"The buffers").

Kept apart from engine/plc_trace.py so the `clr` import sits in one small
function: CPython tests hand the trip a fake in place of `setter_for`, and
nothing here has a fallback for when `clr` is absent, because inside an IDE it
never is.
"""
from __future__ import print_function

MEMBER = "PerformWithWriteableCopy"


def setter_for(api):
    """set_buffers(ring, per_variable) for this trace, or None.

    None when this IDE's trace plug-in has no such member, which the caller
    refuses on: recording with the default ring would silently lose samples,
    and that is the failure the command exists to prevent.
    """
    import clr
    from System import Array
    from System.Reflection import BindingFlags
    method = clr.GetClrType(type(api)).GetMethod(
        MEMBER, BindingFlags.NonPublic | BindingFlags.Instance)
    if method is None:
        return None
    # The parameter is an Action<ITraceObject7>; wrapping the Python function
    # in that delegate type is what lets Invoke accept it.
    action = clr.GetPythonType(method.GetParameters()[0].ParameterType)

    def set_buffers(ring, per_variable):
        def change(writable):
            # Without the override flag the runtime computes its own ring
            # size and ignores uiBufferEntries (research 2.2).
            writable.TraceSettings.bOverrideRTSBufferSize = True
            writable.Record.uiBufferEntries = ring
            writable.TraceSettings.uiBufferPerVariable = per_variable
        method.Invoke(api, Array[object]([action(change)]))
    return set_buffers
