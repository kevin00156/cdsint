# -*- coding: utf-8 -*-
"""The cds-sync-* project properties, as a person sets them (SPEC 6.7).

This used to be two entries of its own in the Scripts menu, which meant a
first-time user had to know to run Project_directory.py before export would
work, and the error message that told them so was the only documentation.
Now export and import ask for the folder themselves when it is missing, and
the watcher's status window has a Settings button for the rest.

Nothing here is reachable with nobody at the keyboard: every dialog goes
through codesys_ui.show_sync_folder_dialog or show_settings_dialog, and
cds/ide/silent.py refuses the first of those outright rather than freezing
the IDE on a modal window (SPEC 6.7 step 1).
"""
from __future__ import print_function

import os

from cds.core import props
from engine.codesys_constants import SCRIPT_VERSION
from engine.codesys_utils import (
    safe_str, get_project_prop, set_project_prop, resolve_projects,
    resolve_system, ensure_git_configs, log_warning,
    update_application_count_flag
)

SETTINGS = (
    # property                 dialog key            default
    (props.EXPORT_XML, "export_xml", False),
    (props.BACKUP_BINARY, "backup_binary", False),
    (props.SAVE_AFTER_IMPORT, "save_after_import", True),
    (props.SAVE_AFTER_EXPORT, "save_after_export", True),
    (props.SAFETY_BACKUP, "safety_backup", True),
    (props.BACKUP_NAME, "backup_name", ""),
    (props.BACKUP_RETENTION_COUNT, "retention_count", 10),
    (props.DEBUG, "debug", False),
)


def _ide(caller_globals):
    """The IDE's `system`, or a loud failure: everything here needs a screen."""
    system = resolve_system(caller_globals)
    if system is None:
        raise RuntimeError(
            "the CODESYS `system` object is not reachable, so there is no "
            "way to put a dialog on screen; settings can only be changed "
            "from inside a running IDE")
    return system


def choose_sync_folder(caller_globals=None):
    """Ask where the sync folder is and remember it.

    Returns (folder, error), the same shape load_base_dir uses, so a caller
    that gives up has a sentence saying which of the three ways this can
    fail happened rather than one flat "not set".

    Called on the first export or import of a project, and again when
    load_base_dir finds the saved path belongs to another computer.
    """
    system = _ide(caller_globals)
    projects_obj = resolve_projects(None, caller_globals)
    if projects_obj is None or not projects_obj.primary:
        failed = "No project open! Open a project to set its sync folder."
        system.ui.error(failed)
        return None, failed

    from engine.codesys_ui import show_sync_folder_dialog
    chosen = show_sync_folder_dialog(system, get_project_prop(props.FOLDER, ""))
    if not chosen:
        print("Sync folder setup cancelled.")
        return None, "Sync folder setup cancelled; nothing was changed."

    folder = _as_written(chosen, projects_obj.primary)
    if not set_project_prop(props.FOLDER, folder):
        failed = ("Could not write cds-sync-folder to Project Information > "
                  "Properties.")
        system.ui.error(failed)
        return None, failed
    _remember_who_and_what()
    _prepare(folder, projects_obj.primary)

    print("Sync folder set to: " + folder)
    system.ui.info("Sync folder saved to Project Information > Properties.\n\n"
                   + folder)
    return folder, None


def edit(caller_globals=None):
    """Open the settings dialog and write back whatever comes out of it."""
    system = _ide(caller_globals)
    try:
        from engine.codesys_ui import show_settings_dialog
    except ImportError as e:
        system.ui.error("Could not load the settings dialog "
                        "(System.Windows.Forms): " + safe_str(e))
        return False

    current = {}
    for prop, key, default in SETTINGS:
        current[key] = get_project_prop(prop, default)
    folder_before = get_project_prop(props.FOLDER, "")
    current["sync_folder"] = folder_before

    chosen = show_settings_dialog(current, version=SCRIPT_VERSION,
                                  system=system)
    if not chosen:
        print("Settings cancelled.")
        return False
    for prop, key, _default in SETTINGS:
        set_project_prop(prop, chosen[key])
    projects_obj = resolve_projects(None, caller_globals)
    _apply_folder(system, chosen.get("sync_folder", ""), folder_before,
                  projects_obj.primary if projects_obj else None)
    print("Settings saved.")
    return True


def _apply_folder(system, typed, before, project):
    """Move the sync folder, but only when the text actually changed.

    Comparing the raw text rather than what _as_written makes of it is
    deliberate. An untouched box must write nothing at all: _prepare creates
    the folder and _remember_who_and_what stamps this machine and this tool
    version onto the project, and doing either on every visit to the dialog
    would let opening Settings quietly claim a project somebody else set up.
    """
    if typed == before:
        return False
    if not typed:
        system.ui.warning("The sync folder was left blank, so it was not "
                          "changed. Type a path, or use Browse.")
        return False
    folder = _as_written(typed, project)
    if not set_project_prop(props.FOLDER, folder):
        system.ui.error("Could not write cds-sync-folder to Project "
                        "Information > Properties.")
        return False
    _remember_who_and_what()
    _prepare(folder, project)
    print("Sync folder set to: " + folder)
    return True


def folder_was_set(caller_globals=None):
    """Finish what `cdsint config set cds-sync-folder=...` started.

    That command writes the property and nothing else, because cds/ide may
    not import the engine (SPEC D12) and everything below this line is engine
    work. Without it a project set up from the CLI came out missing
    cds-sync-pc and cds-sync-version, and with no folder on disk and no git
    rules in it — the same project set up from the dialog has all four. One
    way to do a thing, so this is the dialog's own tail, pressed by name.
    """
    from engine import entry
    # globals() is the namespace cds/ide/silent.py exec'd this file into, and
    # `projects` is in it -- the same way every other entry body finds it.
    projects_obj = resolve_projects(None, caller_globals or globals())
    project = projects_obj.primary if projects_obj else None
    folder = get_project_prop(props.FOLDER, "")
    if not folder:
        return entry.result(False, "cds-sync-folder is not set, so there is "
                                   "nothing to prepare")
    _remember_who_and_what()
    _prepare(folder, project)
    return entry.result(True, "sync folder ready: " + folder, folder=folder)


def _as_written(chosen, project):
    """The path as it goes into the property: relative when it can be.

    A relative path travels with the project -- load_base_dir resolves it
    against the project file and skips the computer-mismatch dialog
    entirely. Only a folder at or under the project's own directory has a
    relative form worth writing; anything else, or another drive, stays
    absolute.
    """
    chosen = chosen.strip().replace("/", os.sep)
    if chosen.startswith("." + os.sep) or chosen == ".":
        return chosen  # already relative; the user typed it that way
    project_dir = _project_dir(project)
    if not project_dir or not os.path.isabs(chosen):
        return chosen
    try:
        inside = os.path.relpath(chosen, project_dir)
    except ValueError:
        return chosen  # another drive: os.path.relpath refuses, rightly
    if inside.startswith(".."):
        return chosen
    return "." + os.sep if inside == "." else "." + os.sep + inside


def _project_dir(project):
    try:
        return os.path.dirname(safe_str(project.path))
    except AttributeError:
        return None


def _remember_who_and_what():
    """Stamp the machine and the tool version this folder was set up with.

    load_base_dir warns when the machine changed and an absolute path is
    probably wrong for this one; check_version_compatibility warns when the
    files on disk were written by a different version. Both need a value
    here to have anything to compare against.
    """
    try:
        import socket
        set_project_prop(props.PC, socket.gethostname())
    except Exception as e:
        log_warning("Could not record the computer name: " + safe_str(e))
    set_project_prop(props.VERSION, SCRIPT_VERSION)


def _prepare(folder, project):
    """Make the folder usable: create it, give it git rules, count the apps."""
    resolved = folder
    if not os.path.isabs(resolved):
        project_dir = _project_dir(project)
        if not project_dir:
            return
        resolved = os.path.normpath(os.path.join(project_dir, resolved))
    if not os.path.exists(resolved):
        os.makedirs(resolved)
    ensure_git_configs(resolved)
    update_application_count_flag()
