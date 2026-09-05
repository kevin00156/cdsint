# -*- coding: utf-8 -*-
"""Lend an entry body the IDE globals it expects, then press its button.

The bodies were menu scripts. CODESYS runs a script by putting `system`,
`projects` and the enum types straight into its namespace, so the bodies read
those as plain globals and pass `globals()` to resolve_projects(). As modules
they have no such namespace of their own, so whoever calls them hands theirs
over.

A name the body already defines wins, which is what the old
`dict(ide_globals)` + exec did: the script's own definitions landed on top of
the IDE's. cds/ide/silent.py does not come through here — it has to install a
stand-in `system` before the body's module-level code runs, so it still execs
the file into a namespace it built itself.
"""
from __future__ import print_function


def run(module, ide_globals, entry="main"):
    """Call module.<entry>() with ide_globals visible in the module."""
    lend(module, ide_globals)
    return getattr(module, entry)()


def lend(module, ide_globals):
    """Copy the IDE's globals onto the module, without shadowing its own."""
    for name in ide_globals:
        if not name.startswith("__") and not hasattr(module, name):
            setattr(module, name, ide_globals[name])
    return module
