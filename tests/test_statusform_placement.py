# -*- coding: utf-8 -*-
"""Where the status window keeps its position, and when it gives that up.

Only the path and the arithmetic. The window itself is WinForms and needs a
real IDE.
"""
import os

import pytest

from cds.core import ipc
from cds.ide import statusform


@pytest.mark.parametrize("suffix", ["", os.sep])
def test_the_placement_file_is_beside_the_instances_root(tmp_path, monkeypatch,
                                                         suffix):
    root = os.path.join(str(tmp_path), "instances")
    monkeypatch.setenv(ipc.ROOT_ENV, root + suffix)
    assert os.path.dirname(statusform.placement_path()) == str(tmp_path)


LAPTOP = [(0, 0, 1920, 1040)]
LEFT_OF_LAPTOP = [(0, 0, 1920, 1040), (-1280, 0, 1280, 984)]


def test_a_window_inside_the_screen_stays_where_it_was_dragged():
    assert statusform.on_screen(100, 100, LAPTOP)


def test_a_window_saved_past_the_right_edge_is_not_on_screen():
    # The field case: x=1904 on a 1920-wide laptop shows 16 pixels at most.
    assert not statusform.on_screen(1904, 17, LAPTOP)


def test_a_window_on_a_monitor_left_of_the_main_one_is_on_screen():
    assert statusform.on_screen(-1000, 100, LEFT_OF_LAPTOP)


def test_that_monitor_unplugged_takes_the_window_off_screen():
    assert not statusform.on_screen(-1000, 100, LAPTOP)


def test_a_window_under_the_taskbar_is_not_on_screen():
    assert not statusform.on_screen(100, 1000, LAPTOP)


def test_no_screens_at_all_is_not_on_screen():
    assert not statusform.on_screen(0, 0, [])
