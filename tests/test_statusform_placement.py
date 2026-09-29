# -*- coding: utf-8 -*-
"""Where the status window keeps its position: beside the root, never in it.

Only the path. The window itself is WinForms and needs a real IDE.
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
