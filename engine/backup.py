# -*- coding: utf-8 -*-
"""Keeping a copy of the .project before anything writes to it.

The whole of it: make one, and throw the oldest away once there are more than
the settings file asked for. It lived among sixteen other jobs in
codesys_utils.py, and everything outside those sixteen used exactly two of
its names -- which is what a seam looks like.

The copy is of the binary .project, not of the sync folder. Disk is the source
of truth for the text (PRINCIPLES 5); this is for the half of the project the
text does not describe.

The two entry points at the bottom are here rather than in codesys_utils.py
because they are what the backups are for: finishing a sync (save the project,
keep a copy) and guarding an import before it changes anything.
"""
from __future__ import print_function

import os
import shutil

from engine.codesys_utils import log_error, log_info, log_warning, safe_str


def cleanup_old_backups(project_folder, retention_count):
    """
    Clean up old timestamped backups in .project/ folder.
    Only deletes files matching pattern: YYYYMMDD_HHMMSS_*.bak
    Preserves non-timestamped backup files (Git LFS backups).
    
    Args:
        project_folder: Path to the .project folder
        retention_count: Number of timestamped backups to keep
    """
    if retention_count <= 0:
        return
    
    if not os.path.exists(project_folder):
        return
    
    import re
    
    timestamped_backups = []
    try:
        for filename in os.listdir(project_folder):
            if not filename.endswith(".bak"):
                continue
            
            # Pattern: YYYYMMDD_HHMMSS_*.bak
            # Example: 20260325_143022_MyProject.project.bak
            if re.match(r'^\d{8}_\d{6}_.*\.bak$', filename):
                full_path = os.path.join(project_folder, filename)
                if os.path.isfile(full_path):
                    timestamped_backups.append(full_path)
        
        if len(timestamped_backups) <= retention_count:
            return
        
        # Sort by filename (timestamp is encoded in name)
        timestamped_backups.sort(reverse=True)
        
        # Delete files beyond retention count
        files_to_delete = timestamped_backups[retention_count:]
        for file_path in files_to_delete:
            try:
                os.remove(file_path)
                filename = os.path.basename(file_path)
                log_info("Deleted old backup: .project/" + filename)
                print("Deleted old backup: .project/" + filename)
            except Exception as e:
                log_warning("Failed to delete old backup " + file_path + ": " + safe_str(e))
                print("Warning: Failed to delete old backup: " + file_path)
    except Exception as e:
        log_warning("Error during backup cleanup: " + safe_str(e))
        print("Warning: Error during backup cleanup: " + safe_str(e))


def backup_project_binary(export_dir, projects_obj, backup_name="",
                          timestamped=False, retention_count=None):
    """
    Copy the current project binary to /project folder.
    Forces a project save before copying to ensure the backup is current.
    If timestamped=True, creates a backup with date and time.
    
    Args:
        export_dir: Directory where .project folder will be created
        projects_obj: CODESYS projects object
        backup_name: What to call the non-timestamped copy; "" means the
                     project's own filename
        timestamped: If True, create timestamped backup with date and time
        retention_count: Optional. If provided, clean up old timestamped backups
                         keeping only this many (only applies to timestamped backups)
    
    Returns:
        Backup filename if created successfully, None otherwise
    """
    try:
        if not projects_obj or not getattr(projects_obj, "primary", None):
            log_warning("Cannot identify project for backup.")
            print("Debug: Cannot identify project for backup (projects_obj missing or invalid).")
            return None

        # Force save to ensure we backup the latest state
        try:
            projects_obj.primary.save()
            log_info("Project saved for backup.")
        except Exception as e:
            msg = "Could not save project before backup: " + safe_str(e)
            log_warning(msg)
            print("Debug: " + msg)

        if not hasattr(projects_obj.primary, "path") or not projects_obj.primary.path:
            log_warning("Project not saved to disk yet. Skipping binary backup.")
            print("Debug: Project has no path on disk.")
            return None

        project_path = projects_obj.primary.path
        project_folder = os.path.join(export_dir, ".project")
        
        if not os.path.exists(project_folder):
            os.makedirs(project_folder)
            
        # Determine target filename
        if timestamped:
            import time
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            base_name = os.path.basename(project_path)
            # Format: YYYYMMDD_HHMMSS_ProjectName.project.bak
            file_name = "{}_{}.bak".format(timestamp, base_name)
        else:
            custom_name = backup_name
            if custom_name:
                # Ensure it ends with .project
                if not custom_name.lower().endswith(".project"):
                    file_name = custom_name + ".project"
                else:
                    file_name = custom_name
            else:
                file_name = os.path.basename(project_path)
            
        target_path = os.path.join(project_folder, file_name)
        
        shutil.copy2(project_path, target_path)
        log_info("Binary backup created: .project/" + file_name)
        print("Binary backup created: .project/" + file_name)
        
        # Clean up old timestamped backups if retention is specified
        if timestamped and retention_count is not None:
            cleanup_old_backups(project_folder, retention_count)
        
        return file_name
        
    except Exception as e:
        log_error("Warning: Could not create binary backup: " + str(e))
        print("Warning: Could not create binary backup: " + str(e))
        return None


def finalize_sync_operation(base_dir, projects_obj, values, is_import=False):
    """Save the project, or back it up, as the settings say.

    One or the other, not both: the binary backup saves the project itself
    before copying it, so doing the save as well would be two full writes of
    the same file.
    """
    save_after_op = values["save_after_import" if is_import
                           else "save_after_export"]

    if values["backup_binary"] and getattr(projects_obj, 'primary', None):
        try:
            print("Action: Updating binary backup...")
            backup_project_binary(base_dir, projects_obj,
                                  values["backup_name"])
        except Exception as e:
            print("Warning: Could not update binary backup: " + safe_str(e))
    elif save_after_op and getattr(projects_obj, 'primary', None):
        try:
            print("Action: Saving project...")
            projects_obj.primary.save()
            print("Project saved successfully.")
        except Exception as e:
            op_str = "import" if is_import else "export"
            print("Warning: Could not save project after " + op_str + ": " + safe_str(e))


def create_safety_backup(base_dir, projects_obj, items_to_import, values):
    """Create a timestamped safety backup of the project before importing changes."""
    if not values["safety_backup"] or not items_to_import:
        return None
    return backup_project_binary(
        base_dir, projects_obj, values["backup_name"], timestamped=True,
        retention_count=values["backup_retention_count"])
