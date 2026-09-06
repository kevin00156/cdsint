# -*- coding: utf-8 -*-
"""cds.ide — the ONLY layer allowed to touch the CODESYS API.

    watcher     what one tick does: claim a command, answer it, beat
    session     arming a watcher in a live IDE and taking it back out
    headless    the IDE side of a --project run: open, run the list, report
    entries     which engine body each command presses, and its result record
    permit      whether this project allows a PLC command, and the refusal
    silent      running an engine body with nobody there to click its dialogs
    outcome     what one such run hands back
    tee         watching its stdout go past and keeping the last of it
    project     asking the IDE what it has open
    messages    reading the build's errors, and writing to the Messages panel
    display     what the status window should say right now
    statusform  the little window that says the watcher is alive

Only session and statusform need .NET; the rest take the CODESYS globals as
an argument, which is what lets CPython test them. IronPython 2.7 throughout.
"""

from __future__ import print_function
