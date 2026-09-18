# -*- coding: utf-8 -*-
"""The ranked cost report the perf probe prints and writes.

Text out of the numbers perf_patch.py recorded: one table ranked by exclusive
time, one by calls, and the buckets that say how often the cache skipped.

Moved out of perf_probe.py unchanged.
"""
from __future__ import print_function

from perf_patch import _stats, _tallies, _timer


def build_report(mode, wall_seconds, object_count, functions, sites,
                 tree_seconds=0.0, interaction_seconds=0.0):
    lines = []
    add = lines.append

    add("=" * 78)
    add("PERF PROBE  --  mode=%s" % mode)
    add("=" * 78)
    add("wall clock      : %.2f s%s"
        % (wall_seconds,
           ("   (excludes %.2f s waiting on dialogs)" % interaction_seconds)
           if interaction_seconds >= 0.05 else ""))
    add("IDE objects     : %s" % (object_count if object_count is not None else "n/a"))
    add("probes active   : %d functions across %d bound names" % (functions, sites))
    add("timer           : %s" % getattr(_timer, "__name__", "?"))
    add("")
    add("EXCL = time inside the function itself (nested probes subtracted).")
    add("INCL = wall time including everything it called.")
    add("Rank by EXCL for cost; read CALLS for per-object IDE round-trips.")
    add("")

    rows = []
    for label in _stats:
        s = _stats[label]
        rows.append((s["excl"], s["incl"], s["calls"], label))
    rows.sort(reverse=True)

    add("-" * 78)
    add("%-34s %8s %10s %10s %9s" % ("FUNCTION", "CALLS", "EXCL(s)", "INCL(s)", "us/call"))
    add("-" * 78)
    for excl, incl, calls, label in rows:
        per_call = (incl / calls * 1000000.0) if calls else 0.0
        add("%-34s %8d %10.3f %10.3f %9.1f" % (label, calls, excl, incl, per_call))

    total_excl = sum(r[0] for r in rows)
    add("-" * 78)
    add("%-34s %8s %10.3f" % ("total measured (excl)", "", total_excl))
    if wall_seconds > 0:
        add("%-34s %8s %10.3f  (%.0f%% of wall clock)"
            % ("unmeasured", "", max(0.0, wall_seconds - total_excl),
               100.0 * max(0.0, wall_seconds - total_excl) / wall_seconds))
    if tree_seconds:
        add("")
        add("get_children(recursive=True) sampled separately: %.3f s" % tree_seconds)
        add("  A method on the project object, so it cannot be wrapped. The")
        add("  engine makes this same call inside the measured region, so")
        add("  expect roughly this much of 'unmeasured' to be it.")

    if _tallies:
        add("")
        add("-" * 78)
        add("RETURN-VALUE TALLIES")
        add("-" * 78)
        for label in sorted(_tallies):
            buckets = _tallies[label]
            total = sum(buckets.values())
            add("  %s  (%d calls)" % (label, total))
            pairs = sorted(buckets.items(), key=lambda kv: -kv[1])
            for bucket, count in pairs:
                share = (100.0 * count / total) if total else 0.0
                add("      %-26s %6d  %5.1f%%" % (bucket, count, share))

    # ── the two numbers that decide the whole diagnosis ──
    add("")
    add("=" * 78)
    add("KEY RATIOS")
    add("=" * 78)

    # An import is two phases with unrelated cost drivers. Which one dominates
    # decides whether to look at the comparison or at the applying of changes.
    compare_phase = _stats.get("compare:find_all_changes")
    apply_phase = _stats.get("import:perform_import_items")
    if compare_phase or apply_phase:
        if compare_phase:
            add("phase 1 find_all_changes : %6.2f s  -- read-only, scales with "
                "project size" % compare_phase["incl"])
        if apply_phase:
            add("phase 2 perform_import   : %6.2f s  -- scales with how many "
                "files changed" % apply_phase["incl"])
        add("")

    skip = _tallies.get("mgr:_try_cache_skip", {})
    if skip:
        hits = skip.get("SKIPPED (cache hit)", 0)
        total = sum(skip.values())
        add("cache skip rate        : %d/%d  (%.1f%%)"
            % (hits, total, 100.0 * hits / total if total else 0.0))
        add("   On an unchanged second run this should be near 100%.")
        add("   Near 0%% means the cache is being rejected, not that work is needed.")

    objs = object_count or 0
    for label, note in [
        ("IDE:read_ide_attrs", "per-object build_properties reads"),
        ("path:get_container_prefix", "parent-chain walks to the project root"),
        ("content:export_object_content", "textual decl/impl extractions"),
        ("tree:find_child_transparent", "sibling scans during tree lookup"),
    ]:
        s = _stats.get(label)
        if s and objs:
            add("%-22s : %d calls = %.2f per object  -- %s"
                % (label.split(":")[-1], s["calls"], float(s["calls"]) / objs, note))

    add("")
    return "\n".join(lines)
