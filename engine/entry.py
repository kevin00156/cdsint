# -*- coding: utf-8 -*-
"""The contract between a caller and one of the entry bodies in engine/.

Two halves. `lend`/`run` give a body the IDE globals it expects: the bodies
were menu scripts, and CODESYS runs a script by putting `system`, `projects`
and the enum types straight into its namespace, so they read those as plain
globals and hand their own `globals()` to borrowed(). As modules they have no
such namespace of their own, so whoever calls them hands theirs over. A name
the body already defines wins, which is what the old `dict(ide_globals)` +
exec did: the script's own definitions landed on top of the IDE's.
cds/ide/silent.py does not come through here — it has to install a stand-in
`system` before the body's module-level code runs, so it still execs the file
into a namespace it built itself.

`result` is what a body hands back, and both callers read it the same way,
and `flags` is how a body reaches the arguments the command carried.
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


def flags(caller_globals):
    """This run's command arguments, or an empty dict when there are none.

    cds/ide/silent.py injects them into the body's own namespace under
    `command_args`, after the body has been exec'd, so they are read from
    there rather than imported (silent.ARGS_GLOBAL). Run from the Scripts
    menu there is no such global at all, and no flags to find, which is why
    a missing one is empty rather than an error.
    """
    return caller_globals.get("command_args") or {}


def borrowed(caller_globals, name):
    """One of the IDE's globals -- `system`, `projects`, `online` -- by name.

    CODESYS puts them into the namespace of the script it runs, and lend()
    below (or cds/ide/silent.py) puts them into the body's. So the body's own
    globals() is where they are, and it is the only place worth looking.

    The four resolvers this replaced each tried the caller's globals and
    then every module already loaded, until something looked close enough --
    a search for an object the caller was holding all along, and a way to
    pick up a dead one from a previous run in the bargain.

    None when the name is not there; the caller says what that means, because
    they do not agree: an export cannot run without `projects`, and the login
    pre-flight without `online` just means nothing can be logged in.
    """
    return (caller_globals or {}).get(name)


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
