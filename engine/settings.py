# -*- coding: utf-8 -*-
"""This run's settings: the file beside the project, read once and resolved.

`cds/core/settings.py` says what a settings file may contain and how to parse
one. This is the engine's end of it: find the file that belongs to the
project the IDE has open, read it, apply this run's `--sync-dir`, and hand
back values whose types are the schema's types so nothing downstream converts
them again (SPEC D10).

Read once per command and passed to whoever needs it. There is no cache,
because reading a small JSON file is not the expensive boundary — crossing
into .NET is (PRINCIPLES.md 3), and this crosses it once, for the project's
own path, which is then handed down rather than fetched again.

Three answers come back, and they are three because commands treat them
differently: the file is unusable, nobody has chosen a sync folder yet, or
here is the folder. `compare`, `export` and `import` cannot work without the
folder; `build` and `discover` can, and lose only their log. Folding the
first two answers together is what let a misspelt key run a build all the way
to a clean finish.

The one dialog left is the first-run question in `choose_sync_folder`: a
project nobody has set up has no folder to write to and no default worth
guessing (SPEC 6.7). With nobody at the keyboard cds/ide/silent.py refuses it
rather than freezing the IDE on a modal window.
"""
from __future__ import print_function

import os

from cds.core import settings as schema
from engine import entry
from engine.codesys_utils import (
    safe_str, ensure_git_configs
)

# The command argument that overrides sync_folder for this run (SPEC 4.2).
# It is never written back: a copy of a project is the case it exists for,
# and a run that quietly edited the copy's settings would make the next run
# behave differently for no reason the caller could see.
SYNC_DIR_ARG = "sync_dir"

NO_PROJECT = "No project is open, so there are no settings to read."


def prepare(caller_globals):
    """This run's settings and its sync folder: (values, folder, error).

    `error` set means the settings file itself cannot be used, and no command
    may go on. `folder` None with no error means nobody has chosen one yet —
    a refusal for some commands and a missing log for others, so the caller
    decides that, not this function.
    """
    project_path = _project_path(caller_globals)
    if project_path is None:
        return None, None, NO_PROJECT
    values, error = _read(project_path, caller_globals)
    if error:
        return None, None, error
    return _with_folder(values, project_path)


def prepare_asking(caller_globals):
    """prepare(), but a project with no folder yet is asked about.

    Export and import are the two commands that may ask, because they are the
    two a first-time user reaches for and there is a good answer to give
    (SPEC 6.7). The read-only commands must not: a dialog is not something to
    open from a `compare`.
    """
    project_path = _project_path(caller_globals)
    if project_path is None:
        return None, None, NO_PROJECT
    values, error = _read(project_path, caller_globals)
    if not error and "sync_folder" not in values:
        values, error = choose_sync_folder(caller_globals, project_path)
    if error:
        return None, None, error
    return _with_folder(values, project_path)


def load(caller_globals=None):
    """Every setting for the open project, defaults filled in: (values, error).

    A project with no settings file is not an error — it is a project nobody
    has set up yet, and it comes back as the defaults with no `sync_folder`.
    A file that exists and is wrong is an error, and the sentence lists every
    setting cdsint knows (SPEC 4.4).
    """
    project_path = _project_path(caller_globals)
    if project_path is None:
        return None, NO_PROJECT
    return _read(project_path, caller_globals)


def folder_missing(caller_globals):
    """The sentence for a command that cannot work without a sync folder.

    Separate from `prepare` because whether a missing folder is fatal is the
    caller's question: it stops a compare and it does not stop a build.
    """
    return _no_folder(_project_path(caller_globals))


def choose_sync_folder(caller_globals, project_path):
    """Ask where the sync folder is and write it down: (values, error).

    Only `sync_folder` is written. Every other setting stays out of the file
    until somebody decides it, so a reader can tell what was chosen from what
    merely defaulted, and changing a default in the code needs no pass over
    anybody's files (SPEC 4.4).

    The project's path is passed in rather than looked up: the only caller
    reached this by reading that project's settings file, so asking the IDE
    for it a second time could only produce the same answer.
    """
    system = _ide(caller_globals)
    path = schema.path_for(project_path)
    chosen = _ask(system, path)
    if not chosen:
        print("Sync folder setup cancelled.")
        return None, "Sync folder setup cancelled; nothing was changed."

    written = _as_written(chosen, os.path.dirname(project_path))
    try:
        schema.write(path, {"sync_folder": written})
    except (IOError, OSError) as exc:
        failed = "Could not write %s: %s" % (path, safe_str(exc))
        system.ui.error(failed)
        return None, failed

    print("Sync folder set to: " + written)
    system.ui.info("Sync folder saved to " + path + "\n\n" + written
                   + "\n\nThe other settings and their defaults are in the "
                     "settings table in readMe.md; add a key to that file "
                     "when you want to change one.")
    return schema.resolve({"sync_folder": written}), None


def _ask(system, settings_path):
    """Put the folder dialog on screen and hand back what came out of it.

    A seam, and it earns its line: engine.codesys_ui imports clr, which only
    exists inside the IDE, so a test in CI cannot reach past this point any
    other way. cds/ide/silent.py replaces the dialog function itself, one
    level further in, which is why that path is unaffected by this.
    """
    from engine.codesys_ui import show_sync_folder_dialog
    return show_sync_folder_dialog(system, settings_path)


def _read(project_path, caller_globals):
    """Parse this project's settings file, with this run's flag over the top."""
    try:
        written = schema.read(schema.path_for(project_path))
    except schema.Invalid as bad:
        return None, safe_str(bad)
    values = schema.resolve(written)
    override = entry.flags(caller_globals or {}).get(SYNC_DIR_ARG)
    if override:
        values["sync_folder"] = override
    return values, None


def _with_folder(values, project_path):
    """Resolve the folder and make it usable: (values, folder, error)."""
    resolved, error = _folder(values, project_path)
    if error:
        return None, None, error
    return values, resolved, None


def _folder(values, project_path):
    """Where sync_folder points, made real: (absolute path or None, error).

    None with no error is "nobody has chosen one". An error is a folder that
    was chosen and cannot be used, which is a different thing and stops every
    command.
    """
    written = values.get("sync_folder")
    if not written:
        return None, None
    resolved = schema.folder(written, os.path.dirname(project_path))
    if not resolved:
        return None, ("Cannot work out where %s points, because the project "
                      "has no path to resolve it against." % (written,))
    try:
        _prepare_folder(resolved)
    except (IOError, OSError) as exc:
        return None, ("Could not create the sync folder %s: %s"
                      % (resolved, safe_str(exc)))
    return resolved, None


def _no_folder(project_path):
    """The sentence a project with no sync folder gets. It names the file."""
    where = (schema.path_for(project_path) if project_path
             else "its settings file")
    return ("This project has no sync folder yet. Write %s next to the "
            "project with {\"sync_folder\": \"./sync\"}, pass --sync-dir to "
            "use one just for this run, or run export once from the Scripts "
            "menu and it will ask." % where)


def _prepare_folder(resolved):
    """Make the folder usable: create it, and give it its git rules."""
    if not os.path.exists(resolved):
        os.makedirs(resolved)
    ensure_git_configs(resolved)


def _as_written(chosen, project_dir):
    """The path as it goes into the file: relative when it can be.

    A relative path travels with the project -- cds.core.settings.folder
    resolves it against the project file, so a copy taken with its settings
    still points at its own sync folder. Only a folder at or under the
    project's own directory has a relative form worth writing; anything else,
    or another drive, stays absolute.

    What counts as relative is cds.core.settings.is_relative, the same
    predicate the resolver uses, so the shape written here cannot drift from
    the shape that gets read back.
    """
    chosen = chosen.strip().replace("/", os.sep)
    if schema.is_relative(chosen):
        return chosen  # already relative; the user typed it that way
    if not project_dir or not os.path.isabs(chosen):
        return chosen
    try:
        inside = os.path.relpath(chosen, project_dir)
    except ValueError:
        return chosen  # another drive: os.path.relpath refuses, rightly
    if inside.startswith(".."):
        return chosen
    return "." + os.sep if inside == "." else "." + os.sep + inside


def _project_path(caller_globals):
    """The open project's path, or None. The only .NET read in this module."""
    projects_obj = entry.borrowed(caller_globals, "projects")
    primary = getattr(projects_obj, "primary", None) if projects_obj else None
    path = getattr(primary, "path", None)
    return None if path is None else safe_str(path)


def _ide(caller_globals):
    """The IDE's `system`, or a loud failure: the dialog needs a screen."""
    system = entry.borrowed(caller_globals, "system")
    if system is None:
        raise RuntimeError(
            "the CODESYS `system` object is not reachable, so there is no "
            "way to put a dialog on screen; the sync folder can only be "
            "chosen from inside a running IDE")
    return system
