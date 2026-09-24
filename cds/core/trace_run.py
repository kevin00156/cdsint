# -*- coding: utf-8 -*-
"""One `plc trace` recording: its buffers, what they cost, and its wait.

The arithmetic both layers need (SPEC D12): the engine sizes the trace and
paces the recording from it, and CI tests it without an IDE. Why each number
is what it is: SPEC 6.8 "The buffers" and "The controller's memory".
"""
from __future__ import print_function

from cds.core import trace_types

# The IDE's per-variable buffer stops recording when it is full, and a
# recording holds a little more or less than duration_s of samples depending
# on the task's jitter. Twice the ring is room for that and for a task that
# runs faster than its configured period.
IDE_BUFFER_FACTOR = 2

# The trace editor's own default ring; a slow task never gets less than the
# IDE would have given it anyway.
DEFAULT_RING_ENTRIES = 100

# What one ring entry costs beside its values. The timestamp is 8 bytes, and
# the runtime was measured spending 22.5 bytes an entry on 12 bytes of values
# (docs/trace-research.md 13.5), so 12 rather than 8: the estimate guards a
# limit whose overrun stops the controller, and it must not come in under.
ENTRY_OVERHEAD_BYTES = 12

# trace_memory_mb counts in these.
MEGABYTE = 1024 * 1024

MICROSECONDS = 1000000

# The name the recording's wait travels under in an engine body's globals
# (SPEC D5): cds/ide/hold.py puts it there and engine/plc_trace_setup.py
# borrows it, the way the body borrows `online`. Here because both layers may
# import this module and neither may import the other (SPEC D12).
HOLD_GLOBAL = "cdsint_hold_ms"

# One hold of the wait. The research probes recorded 100% of their samples
# holding in steps of this size; the IDE fetches from the controller on its
# own schedule, so a shorter step buys nothing, and a longer one only
# overshoots duration_s by more.
HOLD_MS = 200


def sampling_us(period_us, every_n_cycles):
    """The time between two samples of one variable, in microseconds."""
    return period_us * every_n_cycles


def expected_samples(period_us, every_n_cycles, duration_s):
    """How many samples `duration_s` should produce, rounded up."""
    duration_us = int(round(duration_s * MICROSECONDS))
    return _ceil_div(duration_us, sampling_us(period_us, every_n_cycles))


def buffers(period_us, every_n_cycles, duration_s):
    """(controller ring entries, IDE entries per variable) for this run.

    The ring holds the whole recording, so no stall of the IDE shorter than
    the recording loses a sample.
    """
    ring = max(DEFAULT_RING_ENTRIES,
               expected_samples(period_us, every_n_cycles, duration_s))
    return ring, IDE_BUFFER_FACTOR * ring


def ring_bytes(entries, types):
    """The controller memory a ring of `entries` costs for these types.

    Every type must be one trace_types.SIZES knows; the caller refuses the
    others by name first (trace_types.refusals).
    """
    return entries * (ENTRY_OVERHEAD_BYTES
                      + sum(trace_types.SIZES[kind] for kind in types))


def over_limit(entries, types, limit_mb):
    """Why this ring is too big for `trace_memory_mb`, or None if it fits.

    Before the download, because the runtime allocates the whole ring then
    and does not refuse one it cannot hold.
    """
    cost = ring_bytes(entries, types)
    if cost <= limit_mb * MEGABYTE:
        return None
    return ("the controller's ring of %d entries for these variables is "
            "estimated at %.1f MB, over the limit of %d MB that the settings "
            "key trace_memory_mb sets. The runtime allocates the whole ring "
            "when the trace is downloaded and does not refuse one it cannot "
            "hold, so nothing was downloaded: shorten duration_s, raise "
            "every_n_cycles, record fewer variables, or raise "
            "trace_memory_mb if this controller has the memory"
            % (entries, float(cost) / MEGABYTE, limit_mb))


def wait(hold_ms, clock, seconds, done):
    """Hold until `seconds` have passed on `clock`, or done() says so.

    How many holds it took. done() is asked before every hold: a trace with
    a trigger stops by itself, and the run has no reason to sit out the rest
    of duration_s once it has.

    The loop owns no waiting call of its own (SPEC D5): hold_ms is the one
    cds/ide/hold.py lent this run under HOLD_GLOBAL, and a test hands in one
    that moves a fake clock instead. Here rather than in the engine because
    it is plain arithmetic on a clock, which is what this layer is for.
    """
    started = clock()
    holds = 0
    while not done() and clock() - started < seconds:
        hold_ms(HOLD_MS)
        holds += 1
    return holds


def _ceil_div(numerator, denominator):
    return -(-numerator // denominator)
