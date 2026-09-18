# -*- coding: utf-8 -*-
"""What differs between the IDE and the sync folder, object by object.

find_all_changes() is the one walk both compare and import start from:
changed, new on disk, orphaned in the IDE, and -- when a file left one
place and turned up in another with the same content -- moved.

Moved out of codesys_compare_engine.py unchanged.
"""
from __future__ import print_function

import os
import time
from engine.codesys_constants import (
    IMPLEMENTATION_TYPES,
    TYPE_NAMES,
    KNOWN_TYPE_SUFFIXES,
    kind_of,
)
from engine.sync_cache import (
    build_folder_hashes,
    file_signature,
    load_sync_cache,
    normalize_path,
    save_sync_cache,
)
from engine.ide_hash import get_quick_ide_hash
from engine.st_text import (
    parse_sync_pragmas,
    attrs_from_pragmas,
    build_state_hash,
    render_sync_pragmas,
)
from engine.strings import safe_str, calculate_hash
from engine.sync_log import log_info, log_error, log_warning
from engine.object_paths import clear_path_caches
from engine.classify import collect_accessors, resolve_object
from engine import unhandled
from engine.sync_dir import sync_files
from engine.content_compare import (
    _NATIVE_MGR,
    contents_are_equal,
    get_ide_content,
    read_file,
)


def find_all_changes(base_dir, projects_obj, export_xml=False):
    """
    Direct two-way comparison with Merkle Tree optimization.
    
    1. Pass 1: Quick IDE scan (.text only) and folder hash building.
    2. Pass 2: Comparison using folder hashes to skip unchanged branches.
    3. Pass 3: Disk scan for new files.
    4. Pass 4: Detect moved/renamed files by cross-referencing new_in_ide vs new_on_disk.
    """
    total_start = time.time()
    # Paths are memoized per ancestor; start from a clean slate in case an
    # earlier operation in this session moved objects around.
    clear_path_caches()
    # One read of the open project, handed down. The classifier, the content
    # reader and the managers all need it.
    project = projects_obj.primary
    all_ide_objects = project.get_children(recursive=True)
    
    # Load cache
    cache_data = load_sync_cache(base_dir)
    cached_objects = cache_data["objects"]
    cached_folders = cache_data["folders"]
    cached_types = cache_data.get("types", {})
    
    different = []
    new_in_ide = []
    unchanged_count = 0
    cache_hits = 0
    path_invalidations = 0
    
    ide_paths = {}    # rel_path -> obj
    ide_hashes = {}   # norm_path -> ide_hash
    ide_metadata = {} # norm_path -> (eff_type, is_xml)
    current_types = {} # guid -> (eff_type, is_xml, rel_path)
    property_accessors = {} # (parent_guid, name) -> obj
    
    # ── Pass 1: Quick Batch Scan (IDE only) ──
    print("  Pass 1: Batch hashing IDE objects...")
    p1_start = time.time()
    path_cache_hits = 0
    # Entries this pass will not be able to rewrite, kept so that the file
    # they describe keeps its dirty-file guard (SPEC 6.1). An entry says what
    # the disk held at the last sync; only an export or an import can make
    # that statement newer, and compare does neither. Dropping it is how a
    # look-only command used to disarm the guard for the next export.
    carried_entries = {}

    def carry_over(path):
        if not path:
            return
        norm = normalize_path(path)
        kept = cached_objects.get(norm)
        if kept:
            carried_entries[norm] = kept

    for obj in all_ide_objects:
        obj_guid = None
        # One guard for the whole per-object step, not one around each
        # read inside it. Every attribute of an object whose plugin is
        # missing can raise -- .guid here, .type in classify_object --
        # and this loop is where a command meets the objects it cannot
        # handle. It names them and carries on; giving up on the first
        # one used to lose all 229 (SPEC D13, engine/unhandled.py).
        try:
            obj_guid = safe_str(obj.guid)
        
            decided = resolve_object(obj, obj_guid, cached_types, export_xml,
                                     project)
            eff_type = decided.effective_type
            is_xml = decided.is_xml
            rel_path = decided.rel_path
            if decided.cache == "hit":
                path_cache_hits += 1
            elif decided.cache == "invalidated":
                path_invalidations += 1

            carry_over(rel_path)

            # Whatever export refuses to write, this pass must refuse to look
            # for: pass 2 reads "no disk file" as an orphan and import removes
            # the object. resolve_object is why the two agree.
            if decided.skip_reason:
                continue
        
            # Gathered on this walk, not a second one: the objects are
            # already in hand and every name is a .NET read (PRINCIPLES 3).
            collect_accessors(obj, obj_guid, eff_type, property_accessors)

            # Update type cache with path
            current_types[obj_guid] = (eff_type, is_xml, rel_path)

            norm_path = normalize_path(rel_path)
            ide_paths[rel_path] = obj
            ide_metadata[norm_path] = (eff_type, is_xml)
        
            # Quick hash for ST
            q_hash = get_quick_ide_hash(obj, is_xml)
        
            # For XML objects: use cached ide_hash to allow Merkle skip for mixed folders
            if not q_hash and is_xml:
                cached_entry = cached_objects.get(norm_path)
                if cached_entry:
                    q_hash = cached_entry.get("ide_hash")
                
            ide_hashes[norm_path] = q_hash
        except Exception as exc:
            unhandled.note(obj, exc)
            log_error("Cannot read " + unhandled.name_of(obj) + ": " + safe_str(exc))
            # It never reached Pass 2, so nothing fresh describes its file.
            # The type cache remembers where it used to live; that is enough
            # to keep the old entry alive.
            stale = cached_types.get(obj_guid) if obj_guid else None
            carry_over(stale[2] if stale else None)

    # Build folder hashes (Merkle Tree)
        ide_folder_hashes = build_folder_hashes(ide_hashes)
    log_info("  Pass 1 complete ({} objects, {} path cache hits, {} invalidated) in {:.2f}s".format(
        len(ide_hashes), path_cache_hits, path_invalidations, time.time() - p1_start))

    # ── Pass 2: Comparison ──
    print("  Pass 2: Comparing with disk...")
    p2_start = time.time()
    new_cache_objects = dict(carried_entries)
    
    for rel_path, obj in ide_paths.items():
        norm_path = normalize_path(rel_path)
        eff_type, is_xml = ide_metadata[norm_path]
        file_path = os.path.join(base_dir, rel_path.replace("/", os.sep))
        type_name = TYPE_NAMES.get(eff_type, eff_type[:8])
        
        if os.path.exists(file_path):
            # ── Fast path 1: Folder-level check ──
            # If parent folder hash matches, IDE hasn't changed.
            # We only need to check if disk file changed (mtime).
            parent_folder = "/".join(norm_path.split("/")[:-1])
            folder_match = False
            if parent_folder and parent_folder in ide_folder_hashes:
                if ide_folder_hashes[parent_folder] == cached_folders.get(parent_folder):
                    folder_match = True
            
            # Disk check. file_signature() is the single source of truth for
            # this pair -- computing it here independently is exactly how the
            # export and compare sides ended up writing incompatible values
            # under the same cache key.
            mtime, size = file_signature(file_path)
            cached_entry = cached_objects.get(norm_path)

            disk_unchanged = cached_entry and \
                             cached_entry.get("disk_mtime") == mtime and \
                             cached_entry.get("disk_size") == size
            
            # ── CACHE HIT ──
            if folder_match and disk_unchanged:
                unchanged_count += 1
                cache_hits += 1
                new_cache_objects[norm_path] = cached_entry
                continue
                
            # ── Slow path: Full Comparison ──
            can_have_impl = eff_type in IMPLEMENTATION_TYPES
            ide_content, ide_attrs = get_ide_content(obj, is_xml, property_accessors, project, can_have_impl)
            disk_content = read_file(file_path)

            # For ST files, parse pragmas from disk content for attribute comparison
            disk_attrs = {}
            if not is_xml and disk_content:
                disk_pragmas, _ = parse_sync_pragmas(disk_content)
                disk_attrs = attrs_from_pragmas(disk_pragmas)
                # A kind mismatch is reported, never auto-fixed: recreating
                # an object as another kind would destroy IDE-side state.
                disk_kind = disk_pragmas.get("kind")
                if disk_kind and kind_of(disk_kind) != kind_of(eff_type):
                    log_warning("Kind mismatch for %s: disk pragma says '%s' "
                                "but the IDE object is '%s'. Fix the pragma or "
                                "the IDE object manually."
                                % (rel_path, disk_kind, kind_of(eff_type) or eff_type))

            if contents_are_equal(ide_content, disk_content, is_xml, rel_path, ide_attrs, disk_attrs):
                unchanged_count += 1
                # Update cache. An XML object's ide_hash must be written in the
                # same form NativeManager.export() writes it, or the two sides
                # disagree about a byte-identical object and the folder hash it
                # feeds stops matching -- which costs every OTHER object in that
                # folder its Merkle skip too.
                q_hash = ide_hashes[norm_path]
                if not q_hash:
                    q_hash = (_NATIVE_MGR._hash_content(ide_content, os.path.basename(rel_path))
                              if is_xml else build_state_hash(ide_content, ide_attrs))
                new_cache_objects[norm_path] = {
                    "ide_hash": q_hash,
                    "disk_hash": calculate_hash(disk_content),
                    "disk_mtime": mtime,
                    "disk_size": size
                }
            else:
                # Show the pragmas in the diff viewer so attr-only changes are visible
                full_ide_content = ide_content
                if not is_xml and ide_attrs:
                    full_ide_content = render_sync_pragmas(ide_attrs, ide_content)

                different.append({
                    "name": obj.get_name(), "path": rel_path,
                    "type": type_name, "type_guid": eff_type,
                    "obj": obj, "ide_content": full_ide_content, "disk_content": disk_content,
                    "ide_attrs": ide_attrs, "disk_attrs": disk_attrs
                })
        else:
            new_in_ide.append({
                "name": obj.get_name(), "path": rel_path,
                "type": type_name, "type_guid": eff_type, "obj": obj,
                "is_orphan": True
            })

    # Finalize cache with newly built folder hashes and types
    save_sync_cache(base_dir, new_cache_objects, ide_folder_hashes, current_types)
    
    p2_elapsed = time.time() - p2_start
    total_elapsed = time.time() - total_start
    log_info("  Pass 2 complete in {:.2f}s".format(p2_elapsed))
    log_info("  Sync cache updated: %d hits, %d entries total" % (cache_hits, len(new_cache_objects)))
    print("  Compare engine finished in {:.2f}s".format(total_elapsed))

    # Pass 3: Disk Scan
    new_on_disk = scan_new_disk_files(base_dir, ide_paths)

    # Pass 4: Detect moved/renamed files
    moved, new_in_ide, new_on_disk = detect_moved_files(new_in_ide, new_on_disk)
    if moved:
        log_info("  Detected %d moved/renamed objects" % len(moved))

    return {
        "different": different,
        "new_in_ide": new_in_ide,
        "new_on_disk": new_on_disk,
        "moved": moved,
        "unchanged_count": unchanged_count
    }


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
        
        candidates = disk_by_name.get(base_name, [])
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


def scan_new_disk_files(base_dir, ide_paths):
    """
    Walk the export directory and find .st / .xml files that are
    NOT matching any IDE object path.
    
    Returns:
        list of {"name": str, "path": rel_path, "file_path": abs_path}
    """
    new_files = []
    known_paths = set(ide_paths.keys())

    for rel_path, abs_path in sync_files(base_dir):
        if rel_path in known_paths:
            continue
        name = os.path.splitext(os.path.basename(rel_path))[0]
        if rel_path.endswith(".xml") and "." in name:
            name_part, doc_type = name.rsplit(".", 1)
            if doc_type in KNOWN_TYPE_SUFFIXES:
                name = name_part
        new_files.append({
            "name": name,
            "path": rel_path,
            "file_path": abs_path
        })

    return new_files
