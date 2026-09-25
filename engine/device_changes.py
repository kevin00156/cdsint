# -*- coding: utf-8 -*-
"""Which EtherCAT devices this import changed, for the result (SPEC 6.10).

A register for one command, like engine/unhandled.py: the device pass
starts it, the device manager adds to it, and the import's result reads it
as `devices_changed` and `full_download`.
"""
from __future__ import print_function

from engine.strings import safe_str
from engine.sync_log import log_info

_CHANGED = []


def start():
    del _CHANGED[:]


def changed(name):
    _CHANGED.append(safe_str(name))


def report(project):
    """What the result says about devices: which changed, and whether the
    IDE now needs a full download (research 5.1). None when it cannot say."""
    full = None
    if _CHANGED:
        application = getattr(project, "active_application", None)
        possible = getattr(application, "is_online_change_possible", None)
        full = None if possible is None else not possible
        log_info("Devices changed: %s; full download needed: %s"
                 % (", ".join(_CHANGED), full))
    return {"devices_changed": list(_CHANGED), "full_download": full}
