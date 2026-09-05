# -*- coding: utf-8 -*-
"""The contract between a caller and one of the entry bodies in engine/.

Two halves. `lend`/`run` give a body the IDE globals it expects: the bodies
were menu scripts, and CODESYS runs a script by putting `system`, `projects`
and the enum types straight into its namespace, so they read those as plain
globals and pass `globals()` to resolve_projects(). As modules they have no
such namespace of their own, so whoever calls them hands theirs over. A name
the body already defines wins, which is what the old `dict(ide_globals)` +
exec did: the script's own definitions landed on top of the IDE's.
cds/ide/silent.py does not come through here — it has to install a stand-in
`system` before the body's module-level code runs, so it still execs the file
into a namespace it built itself.

`result` is what a body hands back, and both callers read it the same way.
"""
from __future__ import print_function


def result(ok, summary, **data):
    """What every entry body returns (SPEC D11).

    `ok` is the verdict, and it is the only one: the stand-in UI used to
    infer it from message levels, which made "warning" a word no author
    could use without turning a good run into exit 1.

    `summary` is the one line a person reads. When `ok` is false it is also
    the error text the caller gets, so it has to say what went wrong.

    `data` is this command's own counts. Keep the values flat — the CLI
    prints one line per key.
    """
    return {"ok": bool(ok), "summary": summary, "data": data}


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
