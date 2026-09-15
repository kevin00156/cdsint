# -*- coding: utf-8 -*-
"""Keeping a copy of the .project before anything writes to it.

The whole of it: make one, and throw the oldest away once there are more than
the settings file asked for. It lived among sixteen other jobs in
codesys_utils.py, and everything outside those sixteen used exactly two of
its names -- which is what a seam looks like.

The copy is of the binary .project, not of the sync folder. Disk is the source
of truth for the text (PRINCIPLES 5); this is for the half of the project the
text does not describe.

Saving and copying are two jobs with two ways to fail, so they are two
functions and each hands back the reason it could not do its half. Nothing in
here answers trouble with a falsy value: the caller cannot tell "the settings
said not to" from "the disk said no", and it was reading the second as the
first.

The two entry points at the bottom are here rather than in codesys_utils.py
because they are what the backups are for: finishing a sync (save the project,
keep a copy) and guarding an import before it changes anything.
"""
from __future__ import print_function

import os
import re
import shutil
import time

from engine.codesys_utils import log_info, log_warning, safe_str

# YYYYMMDD_HHMMSS_<project name>.bak -- the ones cleanup may delete. A backup
# without the stamp was named by a person (or by Git LFS) and is not ours to
# throw away.
STAMPED = re.compile(r"^\d{8}_\d{6}_.*\.bak$")


def target_name(project_path, backup_name, timestamped, now):
    """What to call this copy of the .project.

    `now` comes from the caller rather than the clock so the name is a
    function of its arguments and a test can spell out the answer.
    """
    if timestamped:
        return "{}_{}.bak".format(time.strftime("%Y%m%d_%H%M%S", now),
                                  os.path.basename(project_path))
    if not backup_name:
        return os.path.basename(project_path)
    if backup_name.lower().endswith(".project"):
        return backup_name
    return backup_name + ".project"


def save_project(projects_obj):
    """Write the open project to disk. None, or why it could not be written.

    The wide `except Exception` is the .NET boundary: save() is a CODESYS call
    and what comes back out of it is not a Python exception hierarchy anybody
    here can enumerate. It does not end here -- it becomes the string the
    caller returns.
    """
    try:
        projects_obj.primary.save()
    except Exception as e:
        message = "could not save the project: " + safe_str(e)
        log_warning(message)
        return message
    log_info("Project saved.")
    return None


def copy_project(project_path, export_dir, file_name):
    """Copy the .project binary into <export_dir>/.project/.

    None, or why the copy did not land.
    """
    project_folder = os.path.join(export_dir, ".project")
    target_path = os.path.join(project_folder, file_name)
    try:
        if not os.path.exists(project_folder):
            os.makedirs(project_folder)
        shutil.copy2(project_path, target_path)
    except (OSError, IOError) as e:
        message = ("could not copy the project to .project/" + file_name
                   + ": " + safe_str(e))
        log_warning(message)
        return message
    log_info("Binary backup created: .project/" + file_name)
    print("Binary backup created: .project/" + file_name)
    return None


def cleanup_old_backups(project_folder, retention_count):
    """Delete timestamped backups past the retention count.

    An old backup that will not go away endangers nothing, so this one logs
    and carries on rather than failing the sync. It catches OSError and not
    Exception because a bug in here is not a busy disk and should not get
    filed as one.
    """
    if retention_count <= 0 or not os.path.exists(project_folder):
        return
    try:
        names = sorted(os.listdir(project_folder), reverse=True)
    except OSError as e:
        log_warning("Could not read " + project_folder + ": " + safe_str(e))
        return

    stamped = []
    for name in names:
        full_path = os.path.join(project_folder, name)
        if STAMPED.match(name) and os.path.isfile(full_path):
            stamped.append(full_path)

    for full_path in stamped[retention_count:]:
        name = os.path.basename(full_path)
        try:
            os.remove(full_path)
        except OSError as e:
            log_warning("Failed to delete old backup " + name + ": "
                        + safe_str(e))
            print("Warning: Failed to delete old backup: " + name)
            continue
        log_info("Deleted old backup: .project/" + name)
        print("Deleted old backup: .project/" + name)


def create_safety_backup(base_dir, projects_obj, items_to_import, values):
    """The copy taken before an import changes anything.

    `(filename, error)`, exactly one of them set -- except when there is
    nothing to guard, which is both of them None: the setting is off, or the
    import has no items. That is the one case the caller may go on from.
    """
    if not values["safety_backup"] or not items_to_import:
        return None, None

    primary = getattr(projects_obj, "primary", None) if projects_obj else None
    if primary is None:
        return None, "no project is open"

    error = save_project(projects_obj)
    if error:
        return None, error

    project_path = getattr(primary, "path", None)
    if not project_path:
        return None, "the project has never been saved to disk"

    file_name = target_name(project_path, values["backup_name"], True,
                            time.localtime())
    error = copy_project(project_path, base_dir, file_name)
    if error:
        return None, error

    cleanup_old_backups(os.path.join(base_dir, ".project"),
                        values["backup_retention_count"])
    return file_name, None


def finalize_sync_operation(base_dir, projects_obj, values, is_import=False):
    """End of a sync: save the project, and copy it if the settings say so.

    None, or why one of the two did not happen.

    Save and copy used to be an if/elif, so that with the binary backup on the
    only save was the one buried inside the copy -- and when that save failed
    the copy went ahead and preserved the previous contents of the file. They
    are two calls now: the save happens whenever either setting wants it, and
    a save that failed stops the copy, because a copy of a stale file is worse
    than no copy at all.
    """
    save_after_op = values["save_after_import" if is_import
                           else "save_after_export"]
    backup_binary = values["backup_binary"]
    if not save_after_op and not backup_binary:
        return None

    primary = getattr(projects_obj, "primary", None) if projects_obj else None
    if primary is None:
        return "no project is open"

    print("Action: Saving project...")
    error = save_project(projects_obj)
    if error:
        return error
    print("Project saved successfully.")
    if not backup_binary:
        return None

    project_path = getattr(primary, "path", None)
    if not project_path:
        return "the project has never been saved to disk"

    print("Action: Updating binary backup...")
    return copy_project(project_path, base_dir,
                        target_name(project_path, values["backup_name"],
                                    False, time.localtime()))
