# -*- coding: utf-8 -*-
"""Tests for the interaction timer behind the reported "Time elapsed".

Export and import time themselves across a region that contains blocking
dialogs -- the orphan-cleanup prompt, the import confirmation. Those measured
how long a human took to click, so the figure said more about the operator
than the sync. Prompts now go through timed_prompt() and are subtracted.
"""
import pytest

from engine import sync_log


@pytest.fixture(scope="module")
def utils():
    return sync_log


@pytest.fixture(autouse=True)
def fresh_timer(utils):
    utils.reset_interaction_timer()
    yield
    utils.reset_interaction_timer()


class TestInteractionTimer:
    def test_starts_at_zero(self, utils):
        assert utils.get_interaction_seconds() == 0.0

    def test_accumulates_prompt_time(self, utils):
        def slow_prompt():
            import time
            time.sleep(0.05)
            return True

        assert utils.timed_prompt(slow_prompt) is True
        assert utils.get_interaction_seconds() >= 0.04

    def test_passes_arguments_and_returns_value(self, utils):
        def prompt(title, message, flag=None):
            return (title, message, flag)

        result = utils.timed_prompt(prompt, "T", "M", flag=7)
        assert result == ("T", "M", 7)

    def test_accumulates_across_several_prompts(self, utils):
        utils.timed_prompt(lambda: None)
        first = utils.get_interaction_seconds()
        utils.timed_prompt(lambda: None)
        assert utils.get_interaction_seconds() >= first

    def test_counts_time_even_when_the_prompt_raises(self, utils):
        """A dialog that blows up still consumed wall-clock time; losing it
        would make the elapsed figure overstate the sync's own cost."""
        def boom():
            import time
            time.sleep(0.05)
            raise RuntimeError("dialog failed")

        with pytest.raises(RuntimeError):
            utils.timed_prompt(boom)
        assert utils.get_interaction_seconds() >= 0.04

    def test_reset_clears(self, utils):
        utils.timed_prompt(lambda: None)
        utils.reset_interaction_timer()
        assert utils.get_interaction_seconds() == 0.0


class TestFormatElapsed:
    def test_plain_when_no_waiting(self, utils):
        assert utils.format_elapsed(12.345, 0.0) == "12.35 seconds"

    def test_ignores_negligible_waiting(self, utils):
        """Sub-half-second is dialog construction, not a human deciding."""
        assert utils.format_elapsed(12.0, 0.1) == "12.00 seconds"

    def test_reports_material_waiting(self, utils):
        text = utils.format_elapsed(12.0, 4.5)
        assert text == "12.00 seconds (plus 4.50s waiting for input)"

    def test_defaults_to_the_live_accumulator(self, utils):
        utils.reset_interaction_timer()
        assert utils.format_elapsed(1.0) == "1.00 seconds"
