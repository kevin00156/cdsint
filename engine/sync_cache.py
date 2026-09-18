# -*- coding: utf-8 -*-
"""What the last sync saw, so the next one can skip what has not changed.

sync_cache.json holds one entry per exported file -- the file's signature on
disk and the hash of the IDE object it came from -- plus a folder-level hash
tree and the classification of every object. It is local state and gitignored
(SPEC 4.5): a fresh clone has none, and every command has to work without it.

The file signature is the one thing both directions have to agree about. They
used to derive it independently -- int(st.st_mtime) on the export side,
os.path.getmtime() (a float) on the compare side -- so every entry written by
one was rejected by the other and both ran at a 0% hit rate on real projects.
That is why it is one function here and not two.
"""
from __future__ import print_function

import io
import json
import os
import time

from engine.strings import calculate_hash, safe_str
from engine.sync_log import log_info, log_warning

# Cache version - bump when the cache format or hash semantics change to
# force a full rebuild
# 3.1: ide hashes include build_properties (exclude_from_build, etc.)
# 3.2: kind pragma - ambiguous-kind files get a one-time header rewrite
# 3.3: disk_mtime is now milliseconds-since-epoch as an int, produced by
# file_signature(). Older caches stored whole seconds (export) or a float
# (compare), so they are discarded rather than silently mis-compared.
CACHE_VERSION = "3.3"


def file_signature(file_path, stat_info=None):
    """Canonical (disk_mtime, disk_size) pair used to decide whether a file on
    disk still matches its sync-cache entry.

    Every writer and every reader of the cache MUST go through this helper.
    The export side used to compute int(st.st_mtime) while the compare side
    used os.path.getmtime() (a float), and both stored the result under the
    same 'disk_mtime' key. NTFS timestamps almost always carry a fractional
    part, so each side rejected every entry the other had written: an export
    followed by an import followed by an export saw a 0% cache hit rate on
    every single run, in both directions.

    Milliseconds keep sub-second resolution (plain int(st_mtime) would miss an
    edit made within the same second as the cached stamp) while staying an
    integer, which survives the JSON round-trip exactly -- unlike a float,
    where equality would depend on repr() reproducing the same value.
    """
    s = stat_info if stat_info is not None else os.stat(file_path)
    return int(s.st_mtime * 1000), s.st_size


def normalize_path(path):
    """Normalize path separators to forward slashes for cross-platform consistency in cache keys."""
    if path is None: return ""
    return path.replace("\\", "/").strip("/")


def build_folder_hashes(object_hashes):
    """
    Build hierarchical folder hashes from a dictionary of object hashes.
    
    Args:
        object_hashes: dict of {norm_path: content_hash}
    
    Returns:
        dict: {folder_path: folder_hash}
    """
    from collections import defaultdict
    folder_children = defaultdict(list)
    
    for path, o_hash in object_hashes.items():
        if not o_hash: continue
        
        parts = path.split("/")
        # Add hash to all parent folders
        for i in range(1, len(parts)):
            folder_path = "/".join(parts[:i])
            folder_children[folder_path].append(o_hash)
            
    result = {}
    for folder_path, child_hashes in folder_children.items():
        # Folder hash is the hash of sorted child hashes
        sorted_hashes = "|".join(sorted(child_hashes))
        result[folder_path] = calculate_hash(sorted_hashes)
        
    return result


def cached_classification(entry):
    """One cached classification, always (eff_type, is_xml, rel_path).

    JSON hands the tuple back as a list, and older caches stored a shorter
    one. Padding it here is what lets every reader write `entry[2]` instead
    of asking how long it is -- that question used to be asked in three
    places, in the same defensive one-liner, which is three chances for one
    of them to answer it differently.

    None for anything that is not a list at all: a cache file of the wrong
    shape is no cache.
    """
    if not isinstance(entry, (list, tuple)):
        return None
    padded = list(entry) + [None, None, None]
    return tuple(padded[:3])


def load_sync_cache(base_dir):
    """Load the synchronization cache from sync_cache.json in the base directory.

    The cache stores object classifications, so it is only trusted when it was
    built with the same type profile: a profile edit (new GUID alias, changed
    sync direction) changes PROFILE_HASH and forces a full re-classification.
    """
    from engine.codesys_constants import PROFILE_HASH
    cache_path = os.path.join(base_dir, "sync_cache.json")
    empty = {"objects": {}, "folders": {}, "types": {}, "version": CACHE_VERSION}
    if os.path.exists(cache_path):
        try:
            with io.open(cache_path, "r", encoding="utf-8", newline="") as f:
                data = json.load(f)
                cache_version = data.get("version", "1.0")
                if cache_version != CACHE_VERSION:
                    log_info("Cache version mismatch (%s vs %s), triggering full rebuild."
                             % (cache_version, CACHE_VERSION))
                    return empty
                if data.get("profile_hash") != PROFILE_HASH:
                    log_info("Sync cache discarded: type profile changed "
                             "(cache=%s, current=%s) - full re-classification."
                             % (data.get("profile_hash"), PROFILE_HASH))
                    return empty
                types = {}
                for guid, entry in (data.get("types") or {}).items():
                    shaped = cached_classification(entry)
                    if shaped is not None:
                        types[guid] = shaped
                return {
                    "objects": data.get("objects", {}),
                    "folders": data.get("folders", {}),
                    "types": types,
                    "version": cache_version
                }
        except Exception as e:
            log_warning("Could not load sync cache: " + safe_str(e))
    return empty


def save_sync_cache(base_dir, objects_cache, folder_hashes=None, type_cache=None):
    """Save the synchronization cache to sync_cache.json in the base directory."""
    from engine.codesys_constants import PROFILE_HASH
    cache_path = os.path.join(base_dir, "sync_cache.json")
    cache_data = {
        "version": CACHE_VERSION,
        "profile_hash": PROFILE_HASH,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "folders": folder_hashes or {},
        "types": type_cache or {},
        "objects": objects_cache
    }
    try:
        with io.open(cache_path, "w", encoding="utf-8", newline="") as f:
            # Compact, not indented. sync_cache.json is machine-read and
            # gitignored, and every entry carries an mtime that changes each
            # run, so it never produces a readable diff anyway. Indenting cost
            # roughly half a second across the write and the following read,
            # and doubled a 125 KB file.
            json.dump(cache_data, f, separators=(",", ":"))
    except Exception as e:
        log_warning("Could not save sync cache: " + safe_str(e))
