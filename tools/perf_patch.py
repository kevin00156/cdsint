# -*- coding: utf-8 -*-
"""Wrapping the real engine functions in place, and what the wrappers record.

Every function and method in perf_tables.py is rebound to a wrapper that
times it, inclusive and exclusive, in every namespace that imported it.
install_probes() is the one call; unresolved_probes() says which rows of the
table name nothing, so a stale table refuses rather than measuring a hole.

Moved out of perf_probe.py unchanged.
"""
from __future__ import print_function

import sys
import time

from perf_tables import FUNCTIONS, METHODS

# High-resolution timer. On Python 2 / Windows time.clock() is
# QueryPerformanceCounter; time.time() only has ~15 ms granularity there, which
# is far too coarse for per-object calls.
try:
    _timer = time.clock
except AttributeError:
    _timer = time.time


_stats = {}          # label -> {"calls", "incl", "excl"}
_tallies = {}        # label -> {bucket: count}
_stack = []          # accumulated child time of each active frame


def _record(label, elapsed, child):
    s = _stats.get(label)
    if s is None:
        s = _stats[label] = {"calls": 0, "incl": 0.0, "excl": 0.0}
    s["calls"] += 1
    s["incl"] += elapsed
    s["excl"] += (elapsed - child)


def _tally(label, bucket):
    t = _tallies.get(label)
    if t is None:
        t = _tallies[label] = {}
    t[bucket] = t.get(bucket, 0) + 1


def _make_wrapper(label, func, bucket_of=None):
    def wrapper(*args, **kwargs):
        _stack.append(0.0)
        start = _timer()
        try:
            result = func(*args, **kwargs)
            if bucket_of is not None:
                try:
                    _tally(label, bucket_of(result))
                except Exception:
                    pass
            return result
        finally:
            elapsed = _timer() - start
            child = _stack.pop()
            if _stack:
                _stack[-1] = _stack[-1] + elapsed
            _record(label, elapsed, child)
    return wrapper


def _find_function(name):
    """The engine's own copy of `name`, or None when nothing under engine/
    has one.

    Anything under engine/, which is both the codesys_* modules and the entry
    bodies: cleanup_orphaned_files lives in entry_export. What identifies the
    engine's own is not where the name is found but who it says it belongs to.
    """
    for module in list(sys.modules.values()):
        if module is None:
            continue
        try:
            candidate = getattr(module, name, None)
        except Exception:
            continue
        owner = getattr(candidate, "__module__", None) if candidate is not None else None
        if owner and owner.startswith("engine."):
            return candidate
    return None


def _find_class(module_name, class_name):
    """The class a methods-table row names, or None if it is not there."""
    module = sys.modules.get(module_name)
    return getattr(module, class_name, None) if module is not None else None


def _patch_function(name, label=None, bucket_of=None):
    """Rebind a module-level function in EVERY namespace that imported it.

    `from engine.ide_attrs import read_ide_attrs` copies the function object into
    the importing module, so patching only the defining module would miss most
    call sites. Identity comparison finds them all.
    """
    original = _find_function(name)
    if original is None:
        return 0

    wrapper = _make_wrapper(label or name, original, bucket_of)
    patched = 0
    for module in list(sys.modules.values()):
        if module is None:
            continue
        try:
            if getattr(module, name, None) is original:
                setattr(module, name, wrapper)
                patched += 1
        except Exception:
            continue
    return patched


def _patch_method(module_name, class_name, method_name, label=None, bucket_of=None):
    """Wrap a method on a class. Subclasses that do not override it inherit
    the wrapper automatically."""
    cls = _find_class(module_name, class_name)
    original = cls.__dict__.get(method_name) if cls is not None else None
    if original is None:
        return 0
    label = label or ("%s.%s" % (class_name, method_name))
    setattr(cls, method_name, _make_wrapper(label, original, bucket_of))
    return 1


def unresolved_probes():
    """Probe-table rows that name nothing the engine has any more.

    A stale row does not fail. It measures nothing, prints nothing, and the
    report reads as though that function cost nothing -- which is the silent
    skip PRINCIPLES 6 is about, wearing a diagnostic's hat.
    """
    missing = [name for name, _label in FUNCTIONS
               if _find_function(name) is None]
    for module_name, class_name, method, _label, _bucket in METHODS:
        cls = _find_class(module_name, class_name)
        if cls is None or method not in cls.__dict__:
            missing.append("%s.%s" % (class_name, method))
    return missing


def install_probes():
    """Wrap everything. Returns (functions_patched, sites_rebound).

    A stale table stops the run instead of shrinking the report: a report
    three rows short misleads worse than no report, because the rows it is
    missing are the ones nobody thinks to look for.
    """
    missing = unresolved_probes()
    if missing:
        print("perf_probe: the probe table names nothing in the engine: "
              + ", ".join(missing))
        print("No probes were installed. Fix the tables in perf_tables.py.")
        return 0, 0

    functions = 0
    sites = 0
    for name, label in FUNCTIONS:
        n = _patch_function(name, label)
        if n:
            functions += 1
            sites += n
    for module_name, class_name, method, label, bucket in METHODS:
        n = _patch_method(module_name, class_name, method, label, bucket)
        if n:
            functions += 1
            sites += n
    return functions, sites
