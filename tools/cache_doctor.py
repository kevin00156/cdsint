# -*- coding: utf-8 -*-
"""Offline health check for a sync directory's sync_cache.json. CPython 3 only.

Answers one question without opening CODESYS: *would the cache actually skip
anything on the next run?* It replays both cache-hit predicates against the
real files on disk --- the export-side one from
codesys_managers._try_cache_skip and the compare-side one from
codesys_compare_engine.find_all_changes --- and reports how many objects each
would let through.

The two predicates are not the same expression, so a cache written by one side
can be systematically rejected by the other. That shows up here as a near-100%
miss rate on one side and a near-0% miss rate on the other.

Usage:
    python tools/cache_doctor.py <sync-dir>
    python tools/cache_doctor.py <sync-dir> --list-misses 20
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

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


def mtime_kind(v):
    if isinstance(v, bool):
        return "other"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float(whole)" if float(v).is_integer() else "float(frac)"
    if v is None:
        return "missing"
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

    # ── 1. mtime storage type ────────────────────────────────────────────
    kinds = Counter(mtime_kind(e.get("disk_mtime")) for e in objects.values())
    print("\n" + "-" * 72)
    print("1. disk_mtime storage type")
    print("-" * 72)
    print("   codesys_managers.py:521      writes int(st_mtime)")
    print("   codesys_compare_engine.py:379 writes os.path.getmtime() -> float")
    print("")
    for kind, n in kinds.most_common():
        print("   %-14s %6d  %s %s" % (kind, n, pct(n, len(objects)), bar(n, len(objects))))
    if kinds.get("int") and (kinds.get("float(frac)") or kinds.get("float(whole)")):
        print("\n   [!] MIXED. Entries from both writers are present in one file.")

    # ── 2. replay both cache-hit predicates ──────────────────────────────
    export_hit = export_miss = 0
    compare_hit = compare_miss = 0
    absent = 0
    reasons = defaultdict(list)

    for norm_path, entry in objects.items():
        file_path = os.path.join(base_dir, norm_path.replace("/", os.sep))
        if not os.path.exists(file_path):
            absent += 1
            reasons["file missing on disk"].append(norm_path)
            continue

        st = os.stat(file_path)
        c_mtime = entry.get("disk_mtime")
        c_size = entry.get("disk_size")
        size_ok = (st.st_size == c_size)

        # codesys_managers._try_cache_skip (managers.pyw:547)
        exp_ok = size_ok and (int(st.st_mtime) == c_mtime)
        # codesys_compare_engine.find_all_changes (compare_engine.pyw:343)
        cmp_ok = size_ok and (st.st_mtime == c_mtime)

        export_hit += exp_ok
        export_miss += not exp_ok
        compare_hit += cmp_ok
        compare_miss += not cmp_ok

        if not size_ok:
            reasons["size differs (real edit)"].append(norm_path)
        elif exp_ok != cmp_ok:
            reasons["mtime type mismatch only"].append(norm_path)
        elif not exp_ok:
            reasons["mtime differs on both"].append(norm_path)

    checked = len(objects) - absent
    print("\n" + "-" * 72)
    print("2. would the next run skip anything?  (%d entries with a real file)" % checked)
    print("-" * 72)
    print("   EXPORT  side  _try_cache_skip()   -> int(st_mtime) == cached")
    print("     skip  %6d  %s %s" % (export_hit, pct(export_hit, checked), bar(export_hit, checked)))
    print("     work  %6d  %s" % (export_miss, pct(export_miss, checked)))
    print("   COMPARE side  find_all_changes()  -> st_mtime == cached")
    print("     skip  %6d  %s %s" % (compare_hit, pct(compare_hit, checked), bar(compare_hit, checked)))
    print("     work  %6d  %s" % (compare_miss, pct(compare_miss, checked)))

    divergent = len(reasons["mtime type mismatch only"])
    if divergent:
        print("\n   [!] %d entries (%s) are accepted by one side and rejected by the"
              % (divergent, pct(divergent, checked)))
        print("       other purely because of int-vs-float. These are objects that")
        print("       have NOT changed but will still be fully re-processed.")

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

    healthy = True
    for side, hit in (("export", export_hit), ("compare/import", compare_hit)):
        rate = 100.0 * hit / checked
        state = "ok" if rate >= 80.0 else "DEGRADED"
        print("  %-15s skips %s of unchanged objects   [%s]"
              % (side, pct(hit, checked), state))
        if rate < 80.0:
            healthy = False

    if divergent:
        healthy = False
        print("")
        print("  [!] %s of entries are accepted by one side and rejected by the"
              % pct(divergent, checked))
        print("      other for no reason but int-vs-float on disk_mtime.")
        print("      Each alternation between export and compare/import rewrites")
        print("      the field in the other format, so the two sides keep")
        print("      invalidating each other's work.")

    if healthy:
        print("")
        print("  Cache looks healthy. If sync still feels slow the cost is")
        print("  elsewhere -- run Project_perf_probe.py inside CODESYS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
