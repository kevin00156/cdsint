# -*- coding: utf-8 -*-
"""One version string, two files that have to agree (SPEC 8).

The engine is the single source; pyproject.toml carries a copy because a
build backend cannot import IronPython-shaped code to ask. Nothing keeps the
copy honest except this test.

The copy is read by hand rather than with tomllib: tomllib is 3.11+, and this
test also runs on the Linux loop that guards portability, which may sit on an
older interpreter than the product's floor. One key out of one table does not
need a parser.
"""
import io
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def packaged_version():
    in_project = False
    with io.open(os.path.join(REPO_ROOT, "pyproject.toml"), encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line.startswith("["):
                in_project = line == "[project]"
            elif in_project and line.startswith("version"):
                key, _, value = line.partition("=")
                if key.strip() == "version":
                    return value.strip().strip('"')
    raise AssertionError("pyproject.toml [project] has no version")


def test_pyproject_carries_the_engine_version():
    from engine.codesys_constants import SCRIPT_VERSION
    assert packaged_version() == SCRIPT_VERSION
