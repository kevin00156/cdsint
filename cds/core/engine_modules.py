# -*- coding: utf-8 -*-
"""Forgetting the engine's modules, so the next run re-reads them from disk.

A watcher lives as long as the IDE does, and so does a Scripts menu that has
been used once, so without this, editing engine code means restarting the IDE
to see the change. Three callers need it — cds/ide/entries.py and the two
menu stubs — and each of them had the loop written out.

The package is named, never imported. This layer has no business depending on
the engine and neither has cds/ide (SPEC D12), and naming it is all that is
needed: the modules being dropped are whatever is loaded right now.

Pure Python (PRINCIPLES.md 4): no CODESYS imports.
"""
from __future__ import print_function

import sys

ENGINE_PACKAGE = "engine"


def forget_engine():
    """Drop every loaded engine module from sys.modules."""
    for name in [n for n in sys.modules.keys()
                 if n.split(".")[0] == ENGINE_PACKAGE]:
        del sys.modules[name]
