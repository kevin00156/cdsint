# -*- coding: utf-8 -*-
"""Offline health check for a sync directory's sync_cache.json. CPython 3 only.

Answers one question without opening CODESYS: *would the cache actually skip
anything on the next run?* It asks the engine's own predicate rather than a
copy of it -- codesys_utils.file_signature() is what both export and compare
compare against, so this imports that function and hands it the same two
values the cache holds.

It used to replay two hand-written expressions instead, one per side, because
that was the bug it existed to find: export compared int(st_mtime), compare
compared a float, and each side rejected everything the other had written.
That is fixed, and a diagnostic still replaying the old expressions reports a
war that is over and calls a healthy cache degraded.

Before any of that it checks whether the engine would look at this cache at
all: load_sync_cache() throws the whole file away when the cache version or
the type profile has moved on, and every number below would then be about a
file nobody is going to read.

Usage:
    python tools/cache_doctor.py <sync-dir>
    python tools/cache_doctor.py <sync-dir> --list-misses 20
"""
from __future__ import annotations, print_function

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

# Two lines, the same in every tool here: put this directory where the
# import system will look, then let tools/_root.py put the install root
# there. Neither is on sys.path already — see tools/_root.py.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _root  # noqa: E402,F401

from engine.codesys_constants import PROFILE_HASH  # noqa: E402
from engine.codesys_utils import CACHE_VERSION, file_signature  # noqa: E402

CACHE_NAME = "sync_cache.json"

# An 8-char uppercase-hex string is what calculate_hash()/build_state_hash()
# produce. NativeManager._hash_file() instead returns str(crc32) --- a decimal
# string of 1..10 digits. The two overlap only for all-digit 8-char values,
# so the classification is reported as a cross-tab against the file extension
# rather than trusted on its own.
RE_STATE_HASH = re.compile(r"^[0-9A-F]{8}$")
RE_CRC_DECIMAL = re.compile(r"^[0-9]{1,10}$")


def classify_hash(h):
    """Return 'state_hash' (calculate_hash), 'crc_decimal' (_hash_file),
    'ambiguous', 'empty' or 'other'."""
    if h is None or h == "":
        return "empty"
    if not isinstance(h, str):
        return "other"
    is_state = bool(RE_STATE_HASH.match(h))
    is_crc = bool(RE_CRC_DECIMAL.match(h))
    if is_state and is_crc:
        return "ambiguous"
    if is_state:
        return "state_hash"
    if is_crc:
        return "crc_decimal"
    return "other"


def pct(n, total):
    return "  n/a" if not total else "%5.1f%%" % (100.0 * n / total)


def bar(n, total, width=28):
    if not total:
        return ""
    filled = int(round(width * n / float(total)))
    return "#" * filled + "." * (width - filled)


def load_cache(base_dir):
    path = os.path.join(base_dir, CACHE_NAME)
    if not os.path.exists(path):
        return None, "%s not found in %s" % (CACHE_NAME, base_dir)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except Exception as exc:  # noqa: BLE001 - report, don't crash
        return None, "could not parse %s: %s" % (path, exc)


def scan_disk(base_dir):
    """Every .st/.xml file under base_dir, as normalized relative paths."""
    found = set()
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
        rel_root = os.path.relpath(root, base_dir)
        rel_root = "" if rel_root == "." else rel_root.replace("\\", "/")
        for name in files:
            if not (name.endswith(".st") or name.endswith(".xml")):
                continue
            if name.startswith("."):
                continue
            found.add(("%s/%s" % (rel_root, name)) if rel_root else name)
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(description="Diagnose a sync_cache.json")
    ap.add_argument("sync_dir", help="the export/sync directory")
    ap.add_argument("--list-misses", type=int, default=8, metavar="N",
                    help="show N example entries per miss reason (default 8)")
    args = ap.parse_args(argv)

    base_dir = os.path.abspath(args.sync_dir)
    if not os.path.isdir(base_dir):
        print("error: not a directory: %s" % base_dir)
        return 2

    cache, err = load_cache(base_dir)
    if err:
        print("error: %s" % err)
        return 2

    objects = cache.get("objects") or {}
    folders = cache.get("folders") or {}
    types = cache.get("types") or {}

    print("=" * 72)
    print("CACHE DOCTOR  --  %s" % base_dir)
    print("=" * 72)
    print("cache version : %s" % cache.get("version"))
    print("profile hash  : %s" % cache.get("profile_hash"))
    print("written at    : %s" % cache.get("created"))
    print("objects=%d  folders=%d  types=%d" % (len(objects), len(folders), len(types)))

    if not objects:
        print("\nThe 'objects' section is empty -- nothing can be skipped on the "
              "next run. Every object will take the slow path.")
        return 0

    # -- 1. would the engine read this file at all? -----------------------
    print("")
    print("-" * 72)
    print("1. is this cache still current?")
    print("-" * 72)
    discarded = []
    if cache.get("version") != CACHE_VERSION:
        discarded.append("cache version is %s, the engine writes %s"
                         % (cache.get("version"), CACHE_VERSION))
    if cache.get("profile_hash") != PROFILE_HASH:
        discarded.append("type profile is %s, this install has %s"
                         % (cache.get("profile_hash"), PROFILE_HASH))
    if discarded:
        for line in discarded:
            print("   [!] %s" % line)
        print("")
        print("   load_sync_cache() will discard the whole file and trigger a")
        print("   full rebuild, so everything below describes a cache the next")
        print("   run is not going to read.")
    else:
        print("   version %s and type profile %s both match this install."
              % (CACHE_VERSION, PROFILE_HASH))

    # -- 2. ask the engine's own predicate --------------------------------
    hit = miss = absent = 0
    reasons = defaultdict(list)

    for norm_path, entry in objects.items():
        file_path = os.path.join(base_dir, norm_path.replace("/", os.sep))
        if not os.path.exists(file_path):
            absent += 1
            reasons["file missing on disk"].append(norm_path)
            continue

        # The one comparison both sides make (codesys_utils.file_signature).
        mtime, size = file_signature(file_path)
        if (mtime, size) == (entry.get("disk_mtime"), entry.get("disk_size")):
            hit += 1
            continue

        miss += 1
        if size != entry.get("disk_size"):
            reasons["size differs (a real edit)"].append(norm_path)
        else:
            reasons["same size, later timestamp"].append(norm_path)

    checked = len(objects) - absent
    print("")
    print("-" * 72)
    print("2. would the next run skip anything?  (%d entries with a real file)" % checked)
    print("-" * 72)
    print("   file_signature(path) == (disk_mtime, disk_size) from the cache")
    print("")
    print("     would skip  %6d  %s %s" % (hit, pct(hit, checked), bar(hit, checked)))
    print("     would work  %6d  %s" % (miss, pct(miss, checked)))
    print("")
    print("   A miss is not wrong on its own: a file that really changed has to")
    print("   be re-processed. It is a problem when nobody has touched the tree")
    print("   and the rate is still high.")

    # ── 3. ide_hash format, split by file kind ───────────────────────────
    cross = defaultdict(Counter)
    for norm_path, entry in objects.items():
        ext = "xml" if norm_path.endswith(".xml") else "st"
        cross[ext][classify_hash(entry.get("ide_hash"))] += 1

    print("\n" + "-" * 72)
    print("3. ide_hash format by file kind")
    print("-" * 72)
    print("   state_hash  = build_state_hash()  (written by export .st + compare)")
    print("   crc_decimal = NativeManager._hash_file()  (written by export .xml)")
    print("")
    for ext in sorted(cross):
        total = sum(cross[ext].values())
        print("   .%-4s (%d entries)" % (ext, total))
        for fmt, n in cross[ext].most_common():
            print("       %-12s %6d  %s" % (fmt, n, pct(n, total)))
    if cross.get("xml") and cross["xml"].get("state_hash"):
        print("\n   [!] %d .xml entries carry a state_hash. Export recomputes those"
              % cross["xml"]["state_hash"])
        print("       with _hash_file(), so their folder hash will not match and")
        print("       every object in those folders loses the Merkle skip.")

    # ── 4. coverage vs the actual tree ───────────────────────────────────
    on_disk = scan_disk(base_dir)
    cached_paths = set(objects.keys())
    uncached = on_disk - cached_paths
    stale = cached_paths - on_disk

    print("\n" + "-" * 72)
    print("4. coverage")
    print("-" * 72)
    print("   files on disk        %6d" % len(on_disk))
    print("   entries in cache     %6d" % len(cached_paths))
    print("   on disk, NOT cached  %6d   (always slow path)" % len(uncached))
    print("   cached, no file      %6d" % len(stale))

    # ── 5. examples ──────────────────────────────────────────────────────
    if args.list_misses > 0:
        shown = [(k, v) for k, v in reasons.items() if v]
        if shown or uncached:
            print("\n" + "-" * 72)
            print("5. examples")
            print("-" * 72)
        for reason, paths in sorted(shown, key=lambda kv: -len(kv[1])):
            print("   %s  (%d)" % (reason, len(paths)))
            for p in sorted(paths)[: args.list_misses]:
                print("       %s" % p)
            if len(paths) > args.list_misses:
                print("       ... and %d more" % (len(paths) - args.list_misses))
        if uncached:
            print("   on disk but not in cache  (%d)" % len(uncached))
            for p in sorted(uncached)[: args.list_misses]:
                print("       %s" % p)
            if len(uncached) > args.list_misses:
                print("       ... and %d more" % (len(uncached) - args.list_misses))

    # ── verdict ──────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("VERDICT")
    print("=" * 72)
    if not checked:
        print("No cache entry has a matching file -- nothing to judge.")
        return 0

    healthy = not discarded
    if discarded:
        print("  The engine will discard this cache and rebuild from scratch,")
        print("  so the skip rate below is not what the next run will get.")
        print("")

    rate = 100.0 * hit / checked
    if rate < 80.0:
        healthy = False
    print("  skips %s of the objects it has entries for   [%s]"
          % (pct(hit, checked), "ok" if rate >= 80.0 else "DEGRADED"))

    if healthy:
        print("")
        print("  Cache looks healthy. If sync still feels slow the cost is")
        print("  elsewhere -- run tools/perf_probe.py inside CODESYS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
