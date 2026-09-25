# -*- coding: utf-8 -*-
"""Which files moved: an object missing where the disk expects it and a file
with no object, paired by file name.

Moved out of change_detect.py unchanged, to keep that file under the size
limit; _move_candidates was written here (SPEC 6.9).
"""
from __future__ import print_function

from cds.core.library_list import SUFFIX as LIBRARY_SUFFIX
from engine.sync_log import log_info


def _move_candidates(disk_by_name, base_name):
    """Disk files that could be where this IDE object's file went.

    None for a Library Manager: every one of them is called
    "Library Manager.libraries", so a name match says nothing, and pairing
    them silently dropped a stale file that SPEC 6.9 says must fail by path.
    """
    if base_name.endswith(LIBRARY_SUFFIX):
        return []
    return disk_by_name.get(base_name, [])


def detect_moved_files(new_in_ide, new_on_disk):
    """
    Detect moved/renamed files by cross-referencing objects that exist
    in the IDE but not on disk (new_in_ide) with files on disk that
    don't match any IDE path (new_on_disk).
    
    Matching is done by object base name (case-insensitive).
    
    A "move" is when:
    - IDE has object at path A, but file A doesn't exist on disk
    - Disk has file at path B, but no IDE object maps to path B
    - The base name matches (e.g. same "MyPOU.st" in different folders)
    
    Returns:
        (moved_list, remaining_new_in_ide, remaining_new_on_disk)
        
        moved_list items: {
            "name": str, "ide_path": str, "disk_path": str,
            "type": str, "type_guid": str, "obj": CODESYS obj,
            "file_path": str (absolute), "direction": "ide"|"disk"
        }
    """
    if not new_in_ide or not new_on_disk:
        return [], new_in_ide, new_on_disk
    
    moved = []
    matched_ide_indices = set()
    matched_disk_indices = set()
    
    # Build a lookup from base filename -> list of (index, item) for disk files
    disk_by_name = {}  # base_name_lower -> [(index, item), ...]
    for i, disk_item in enumerate(new_on_disk):
        # Extract base filename from path for matching
        disk_file = disk_item["path"].replace("\\", "/").split("/")[-1]
        base_name = disk_file.lower()
        if base_name not in disk_by_name:
            disk_by_name[base_name] = []
        disk_by_name[base_name].append((i, disk_item))
    
    # Try to match each IDE orphan to a disk orphan by filename
    for ide_idx, ide_item in enumerate(new_in_ide):
        ide_file = ide_item["path"].replace("\\", "/").split("/")[-1]
        base_name = ide_file.lower()
        
        candidates = _move_candidates(disk_by_name, base_name)
        for disk_idx, disk_item in candidates:
            if disk_idx in matched_disk_indices:
                continue
            
            # Match found: same filename, different path
            ide_path = ide_item["path"]
            disk_path = disk_item["path"]
            
            if ide_path == disk_path:
                # Same path — not a move (shouldn't happen but safety check)
                continue
            
            # Determine direction: where is the "correct" location?
            # IDE path = where the object currently lives in IDE
            # Disk path = where the file currently lives on disk
            moved.append({
                "name": ide_item["name"],
                "ide_path": ide_path,
                "disk_path": disk_path,
                "type": ide_item.get("type", "unknown"),
                "type_guid": ide_item.get("type_guid", ""),
                "obj": ide_item.get("obj"),
                "file_path": disk_item.get("file_path", ""),
            })
            
            matched_ide_indices.add(ide_idx)
            matched_disk_indices.add(disk_idx)
            log_info("Detected move: '%s' IDE:'%s' -> Disk:'%s'" % (
                ide_item["name"], ide_path, disk_path))
            break  # One match per IDE item
    
    # Filter out matched items from both lists
    remaining_ide = [item for i, item in enumerate(new_in_ide) if i not in matched_ide_indices]
    remaining_disk = [item for i, item in enumerate(new_on_disk) if i not in matched_disk_indices]
    
    return moved, remaining_ide, remaining_disk
