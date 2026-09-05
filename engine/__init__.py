# -*- coding: utf-8 -*-
"""The sync engine: everything that walks the IDE object tree or touches a PLC.

Runs under the IronPython 2.7 the IDE ships, so Python 2/3 compatible source,
standard library only (SPEC D4). It never imports cds.ide — the dependency
runs the other way, cds/ide drives an entry body by name (SPEC D12).

    codesys_constants   GUID tables and per-kind sync policy, from profiles/
    codesys_utils       paths, hashing, .st formatting, project properties
    codesys_managers    one manager per object kind: read it, write it back
    codesys_compare_engine  what differs between the IDE and the disk
    codesys_ui          the WinForms dialogs a person clicks
    codesys_ui_diff     the side-by-side viewer
    codesys_online      is anyone logged into a PLC right now

    entry_*             the bodies behind the Scripts menu entries. stub/ has
                        the ten-line files the IDE scans; entry.py lends a body
                        the IDE globals it was written to find in its own
                        namespace.
"""

from __future__ import print_function
