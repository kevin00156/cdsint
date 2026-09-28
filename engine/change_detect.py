# -*- coding: utf-8 -*-
"""What differs between the IDE and the sync folder, object by object.

find_all_changes() is the one walk both compare and import start from:
changed, new on disk, orphaned in the IDE, and -- when a file left one
place and turned up in another with the same content -- moved.

Moved out of codesys_compare_engine.py, and split into one function per
pass here.
"""
from __future__ import print_function

import os
import time
from engine.move_detect import detect_moved_files
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
from engine.classify import PathClaims, collect_accessors, resolve_object
from engine import unhandled
from engine.sync_dir import sync_files
from engine.content_compare import (
    _NATIVE_MGR,
    contents_are_equal,
    get_ide_content,
    read_file,
)


class _Scan(object):
    """What Pass 1 learned about the IDE side, for Pass 2 to compare.

    One object rather than seven dicts threaded through every step: each
    step fills or reads several of them, and seven in and seven out of every
    function is a signature nobody can read.
    """

    def __init__(self, cache_data):
        self.cached_objects = cache_data["objects"]
        self.cached_folders = cache_data["folders"]
        self.cached_types = cache_data.get("types", {})
        self.paths = {}      # rel_path -> obj
        self.hashes = {}     # norm_path -> ide_hash
        self.metadata = {}   # norm_path -> (eff_type, is_xml)
        self.types = {}      # guid -> (eff_type, is_xml, rel_path)
        self.accessors = {}  # (parent_guid, name) -> obj
        # Entries this pass will not be able to rewrite, kept so that the
        # file they describe keeps its dirty-file guard (SPEC 6.1). An entry
        # says what the disk held at the last sync; only an export or an
        # import can make that statement newer, and compare does neither.
        # Dropping it is how a look-only command used to disarm the guard
        # for the next export.
        self.carried = {}
        self.path_cache_hits = 0
        self.path_invalidations = 0
        self.claims = PathClaims()

    def carry_over(self, path):
        if not path:
            return
        norm = normalize_path(path)
        kept = self.cached_objects.get(norm)
        if kept:
            self.carried[norm] = kept


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
    scan = _scan_ide(project, load_sync_cache(base_dir), export_xml)

    # Build folder hashes (Merkle Tree)
    ide_folder_hashes = build_folder_hashes(scan.hashes)
    log_info("  Pass 1 complete ({} objects, {} path cache hits, {} invalidated) in {:.2f}s".format(
        len(scan.hashes), scan.path_cache_hits, scan.path_invalidations,
        time.time() - total_start))

    p2_start = time.time()
    found = _compare_all(scan, base_dir, project, ide_folder_hashes)
    log_info("  Pass 2 complete in {:.2f}s".format(time.time() - p2_start))

    # Pass 3: Disk Scan
    new_on_disk = scan_new_disk_files(base_dir,
                                      list(scan.paths) + list(scan.claims.shared))
    # A file no object claims keeps its entry too: that entry is what lets
    # the next export tell an orphan from somebody's new file (orphan_sweep).
    for item in new_on_disk:
        key = normalize_path(item["path"])
        if key in scan.cached_objects:
            found["cache"][key] = scan.cached_objects[key]

    save_sync_cache(base_dir, found["cache"],
                    _recorded_folder_hashes(found["cache"], scan.hashes),
                    scan.types)
    log_info("  Sync cache updated: %d hits, %d entries total"
             % (found["cache_hits"], len(found["cache"])))
    print("  Compare engine finished in {:.2f}s".format(time.time() - total_start))

    # Pass 4: Detect moved/renamed files
    moved, new_in_ide, new_on_disk = detect_moved_files(found["new_in_ide"],
                                                        new_on_disk)
    if moved:
        log_info("  Detected %d moved/renamed objects" % len(moved))

    return {
        "different": found["different"],
        "new_in_ide": new_in_ide,
        "new_on_disk": new_on_disk,
        "moved": moved,
        "unchanged_count": found["unchanged_count"]
    }


def _recorded_folder_hashes(cache, ide_hashes):
    """The folder hashes to save: of the entries this run recorded.

    Not of what the IDE holds now. An object compare found different keeps
    its old entry, and a folder hash that already covered its new state
    matched the next compare's, whose fast path then reported it unchanged.
    Only paths Pass 1 hashes count, so both sides hash the same set.
    """
    return build_folder_hashes(dict(
        (path, entry.get("ide_hash")) for path, entry in cache.items()
        if ide_hashes.get(path)))


def _scan_ide(project, cache_data, export_xml):
    """Pass 1: classify every object and hash what can be hashed cheaply."""
    print("  Pass 1: Batch hashing IDE objects...")
    scan = _Scan(cache_data)
    for obj in project.get_children(recursive=True):
        obj_guid = None
        # One guard for the whole per-object step, not one around each
        # read inside it. Every attribute of an object whose plugin is
        # missing can raise -- .guid here, .type in classify_object --
        # and this loop is where a command meets the objects it cannot
        # handle. It names them and carries on; giving up on the first
        # one used to lose all 229 (SPEC D13, engine/unhandled.py).
        try:
            obj_guid = safe_str(obj.guid)
            _scan_one(obj, obj_guid, scan, export_xml, project)
        except Exception as exc:
            unhandled.note(obj, exc)
            log_error("Cannot read " + unhandled.name_of(obj) + ": " + safe_str(exc))
            # It never reached Pass 2, so nothing fresh describes its file.
            # The type cache remembers where it used to live; that is enough
            # to keep the old entry alive.
            stale = scan.cached_types.get(obj_guid) if obj_guid else None
            scan.carry_over(stale[2] if stale else None)
    # A shared file is compared for neither object: whichever came first
    # would stand for both.
    for rel_path in list(scan.paths):
        if normalize_path(rel_path) in scan.claims.shared:
            del scan.paths[rel_path]
    return scan


def _scan_one(obj, obj_guid, scan, export_xml, project):
    """Pass 1 for one object: where its file is, and its quick hash."""
    decided = resolve_object(obj, obj_guid, scan.cached_types, export_xml,
                             project)
    eff_type = decided.effective_type
    is_xml = decided.is_xml
    rel_path = decided.rel_path
    if decided.cache == "hit":
        scan.path_cache_hits += 1
    elif decided.cache == "invalidated":
        scan.path_invalidations += 1

    scan.carry_over(rel_path)

    # Whatever export refuses to write, this pass must refuse to look
    # for: pass 2 reads "no disk file" as an orphan and import removes
    # the object. resolve_object is why the two agree.
    if decided.skip_reason:
        return

    # Gathered on this walk, not a second one: the objects are
    # already in hand and every name is a .NET read (PRINCIPLES 3).
    collect_accessors(obj, obj_guid, eff_type, scan.accessors)

    scan.types[obj_guid] = (eff_type, is_xml, rel_path)
    if not scan.claims.claim(rel_path, obj_guid, obj):
        return

    norm_path = normalize_path(rel_path)
    scan.paths[rel_path] = obj
    scan.metadata[norm_path] = (eff_type, is_xml)

    scan.hashes[norm_path] = get_quick_ide_hash(obj, is_xml)


def _compare_all(scan, base_dir, project, ide_folder_hashes):
    """Pass 2: every object Pass 1 found, against its file."""
    print("  Pass 2: Comparing with disk...")
    found = {"different": [], "new_in_ide": [], "unchanged_count": 0,
             "cache_hits": 0, "cache": dict(scan.carried)}
    for rel_path, obj in scan.paths.items():
        norm_path = normalize_path(rel_path)
        eff_type, is_xml = scan.metadata[norm_path]
        file_path = os.path.join(base_dir, rel_path.replace("/", os.sep))
        type_name = TYPE_NAMES.get(eff_type, eff_type[:8])

        if not os.path.exists(file_path):
            found["new_in_ide"].append({
                "name": obj.get_name(), "path": rel_path,
                "type": type_name, "type_guid": eff_type, "obj": obj,
                "is_orphan": True
            })
            continue

        # ── Fast path: Folder-level check ──
        # If parent folder hash matches, IDE hasn't changed.
        # We only need to check if disk file changed (mtime). An XML object
        # has no quick hash, so its folder's hash says nothing about it.
        parent_folder = "/".join(norm_path.split("/")[:-1])
        folder_match = not is_xml and bool(parent_folder) and \
            parent_folder in ide_folder_hashes and \
            ide_folder_hashes[parent_folder] == scan.cached_folders.get(parent_folder)

        # Disk check. file_signature() is the single source of truth for
        # this pair -- computing it here independently is exactly how the
        # export and compare sides ended up writing incompatible values
        # under the same cache key.
        signature = file_signature(file_path)
        cached_entry = scan.cached_objects.get(norm_path)
        disk_unchanged = cached_entry and \
            (cached_entry.get("disk_mtime"), cached_entry.get("disk_size")) == signature

        if folder_match and disk_unchanged:
            found["unchanged_count"] += 1
            found["cache_hits"] += 1
            found["cache"][norm_path] = cached_entry
            continue

        item, entry = _compare_file(obj, rel_path, file_path, eff_type, is_xml,
                                    scan, project)
        if item is None:
            found["unchanged_count"] += 1
            entry["disk_mtime"], entry["disk_size"] = signature
            found["cache"][norm_path] = entry
        else:
            item["type"] = type_name
            found["different"].append(item)
    return found


def _compare_file(obj, rel_path, file_path, eff_type, is_xml, scan, project):
    """The slow path. (None, fresh cache entry) when the two sides match,
    (the difference, None) when they do not."""
    can_have_impl = eff_type in IMPLEMENTATION_TYPES
    ide_content, ide_attrs = get_ide_content(obj, is_xml, scan.accessors,
                                             project, can_have_impl)
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
        # An XML object's ide_hash is written in the same form
        # NativeManager.export() writes it, so the two sides' entries agree
        # about a byte-identical object.
        q_hash = scan.hashes[normalize_path(rel_path)]
        if not q_hash:
            q_hash = (_NATIVE_MGR._hash_content(ide_content)
                      if is_xml else build_state_hash(ide_content, ide_attrs))
        return None, {"ide_hash": q_hash,
                      "disk_hash": calculate_hash(disk_content)}

    # Show the pragmas in the diff viewer so attr-only changes are visible
    full_ide_content = ide_content
    if not is_xml and ide_attrs:
        full_ide_content = render_sync_pragmas(ide_attrs, ide_content)

    return {
        "name": obj.get_name(), "path": rel_path,
        "type_guid": eff_type,
        "obj": obj, "ide_content": full_ide_content, "disk_content": disk_content,
        "ide_attrs": ide_attrs, "disk_attrs": disk_attrs
    }, None


def scan_new_disk_files(base_dir, ide_paths):
    """
    Walk the export directory and find .st / .xml files that are
    NOT matching any IDE object path. ide_paths is any iterable of them.

    Returns:
        list of {"name": str, "path": rel_path, "file_path": abs_path}
    """
    new_files = []
    known_paths = set(normalize_path(path) for path in ide_paths)

    for rel_path, abs_path in sync_files(base_dir):
        if normalize_path(rel_path) in known_paths:
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
