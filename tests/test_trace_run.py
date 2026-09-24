# -*- coding: utf-8 -*-
"""One recording's buffers, what they cost the controller, and its wait.

The ring holds the whole recording, because a stalled IDE fetches nothing
and whatever the ring cannot hold until it comes back is lost
(docs/trace-research.md 13.1). The cost is bounded because the runtime does
not refuse a ring it cannot hold (13.5).
"""
import pytest

from cds.core import trace_run


def test_a_one_ms_task_for_three_seconds():
    # The ring: all 3000 samples of the recording. The IDE: twice that.
    assert trace_run.buffers(1000, 1, 3) == (3000, 6000)


def test_sampling_every_second_cycle_halves_the_ring():
    # 4 ms x 2 = 8 ms between samples; 3 s of those is 375.
    assert trace_run.buffers(4000, 2, 3) == (375, 750)


def test_a_slow_task_keeps_the_ides_default_ring():
    # 100 ms: three seconds is 30 samples, below the IDE's own 100.
    assert trace_run.buffers(100000, 1, 3) == (100, 200)


def test_a_long_recording_gets_a_ring_as_long():
    # research 13.1: a 30 s ring rode out a 10 s stall that a 2 s one lost.
    assert trace_run.buffers(1000, 1, 300) == (300000, 600000)


def test_counts_round_up():
    # 3 ms period: 1 s is 333.3 samples.
    assert trace_run.buffers(3000, 1, 1) == (334, 668)
    assert trace_run.expected_samples(3000, 1, 1) == 334


def test_a_float_duration_does_not_pick_up_a_sample_from_rounding():
    # 0.3 * 1000000 is 300000.00000000006 in binary floating point.
    assert trace_run.expected_samples(1000, 1, 0.3) == 300


def test_a_4_ms_task_for_three_seconds():
    assert trace_run.buffers(4000, 1, 3.0) == (750, 1500)


# -- what the ring costs ----------------------------------------------------

def test_ring_bytes_is_entries_times_overhead_and_values():
    # research 13.5's four variables: 2 + 4 + 4 + 2 bytes of values.
    types = ["INT", "UDINT", "DINT", "WORD"]
    assert trace_run.ring_bytes(1000, types) == 1000 * (12 + 12)
    # and it does not come in under what the bench measured: 22.5 an entry
    assert trace_run.ring_bytes(1000, types) >= 1000 * 22.5


def test_ring_bytes_of_no_variables_is_the_overhead():
    assert trace_run.ring_bytes(10, []) == 120


def test_every_size_class_is_counted():
    assert trace_run.ring_bytes(1, ["BOOL", "INT", "REAL", "LREAL"]) == \
        12 + 1 + 2 + 4 + 8


def test_a_ring_under_the_limit_fits():
    assert trace_run.over_limit(1000, ["INT"], 1) is None


def test_a_ring_exactly_at_the_limit_fits():
    entries = trace_run.MEGABYTE // 20          # 12 + 8 bytes an entry
    assert trace_run.over_limit(entries, ["LINT"], 1) is None
    assert trace_run.over_limit(entries + 1, ["LINT"], 1) is not None


def test_a_ring_over_the_limit_names_estimate_limit_and_key():
    # 3600000 entries (an hour at 1 ms) of four variables: research 13.5.
    problem = trace_run.over_limit(3600000, ["INT", "UDINT", "DINT", "WORD"],
                                   64)
    assert "3600000 entries" in problem
    assert "82.4 MB" in problem           # 3600000 * 24 / 2**20
    assert "64 MB" in problem
    assert "trace_memory_mb" in problem
    assert "nothing was downloaded" in problem


# -- the wait ---------------------------------------------------------------

class Clock(object):
    def __init__(self):
        self.now = 1000.0
        self.holds = []

    def __call__(self):
        return self.now

    def hold_ms(self, milliseconds):
        self.holds.append(milliseconds)
        self.now += milliseconds / 1000.0


def never():
    return False


def test_the_wait_loop_counts_on_the_clock_it_is_given():
    clock = Clock()
    assert trace_run.wait(clock.hold_ms, clock, 0.5, never) == 3
    assert trace_run.wait(clock.hold_ms, clock, 0.2, never) == 1
    assert set(clock.holds) == {trace_run.HOLD_MS}


def test_the_wait_ends_when_done_says_so():
    clock = Clock()
    asked = []

    def done():
        asked.append(clock.now)
        return len(asked) > 4

    assert trace_run.wait(clock.hold_ms, clock, 60, done) == 4
    assert len(asked) == 5


def test_a_wait_already_done_holds_not_at_all():
    clock = Clock()
    assert trace_run.wait(clock.hold_ms, clock, 60, lambda: True) == 0


@pytest.mark.parametrize("seconds, holds", [(0.1, 1), (1.0, 5), (1.1, 6)])
def test_the_wait_never_stops_short(seconds, holds):
    clock = Clock()
    assert trace_run.wait(clock.hold_ms, clock, seconds, never) == holds
