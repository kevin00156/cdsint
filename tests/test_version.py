# -*- coding: utf-8 -*-
"""One version string, two files that have to agree (SPEC 8).

The engine is the single source; pyproject.toml carries a copy because a
build backend cannot import IronPython-shaped code to ask. Nothing keeps the
copy honest except this test.
"""
import io
import os
import tomllib

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def packaged_version():
    with io.open(os.path.join(REPO_ROOT, "pyproject.toml"), "rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def test_pyproject_carries_the_engine_version():
    from engine.codesys_constants import SCRIPT_VERSION
    assert packaged_version() == SCRIPT_VERSION
