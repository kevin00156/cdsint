# -*- coding: utf-8 -*-
"""The wait `plc trace` records through: system.delay(), and only without a window.

SPEC D5 bans system.delay() on the IDE side because it pumps repaints but not
mouse and keyboard, so a window stays on screen and cannot be clicked. A
recording has to last `duration_s` seconds, and under --noUI there is no
window to freeze and no message loop to hang a timer on: the script returning
early would end the process. That is D5's second registered exception, and
this file is it. tests/test_single_threaded_ide_side.py allows one `delay`
call here and no more.

The engine never waits itself. It borrows the callable made here from its
globals, under trace_run.HOLD_GLOBAL, exactly as it borrows `online`, so its
recording loop has no waiting call in it and CI runs it on a fake clock.
"""
from __future__ import print_function

from cds.core.trace_run import HOLD_GLOBAL


def lend(ide_globals):
    """Put this run's hold into the globals an engine body will be given.

    None goes in when there is a window, so a body that needs to wait finds
    nothing and refuses by name rather than freezing somebody's IDE.
    """
    ide_globals[HOLD_GLOBAL] = hold_for(ide_globals.get("system"))


def hold_for(system):
    """A function hold_ms(ms) that blocks this --noUI run, or None with a UI.

    An IDE that does not say whether it has a UI is treated as having one:
    the exception exists only for the case that earns it, and "cannot tell"
    is not that case.
    """
    if system is None or getattr(system, "ui_present", True):
        return None

    def hold_ms(milliseconds):
        system.delay(milliseconds)
    return hold_ms
