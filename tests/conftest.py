# -*- coding: utf-8 -*-
"""Shared test helpers: reaching the engine modules by name."""
import importlib

import pytest


def load(module_name):
    """Import one engine module, e.g. load("codesys_utils").

    The engine used to be .pyw files at the repo root, which is not a shape
    importlib can address by name, so every test went through a loader built
    on SourceFileLoader. engine/ is an ordinary package now and this is the
    whole of what is left; the fixture stays only so the test files did not
    all have to change shape at once.
    """
    return importlib.import_module("engine." + module_name)


@pytest.fixture(scope="session")
def load_engine():
    """Session-wide access to load for test modules."""
    return load
