# -*- coding: utf-8 -*-
"""The property names the code uses are the ones SPEC 4.4 documents.

A typo in one of these is invisible: reading a property nobody wrote gives
the default, writing one nobody reads succeeds. Nothing crashes, the setting
just quietly stops working. So the names get a second witness, and the
witness is the specification -- which makes this test fail in both
directions, on a property added to the code without being written down and
on one renamed in the document without being renamed here.
"""
import io
import os
import re

import pytest

from cds.core import props

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(REPO_ROOT, "docs", "SPEC.md")


def documented():
    """Every `cds-sync-*` name in SPEC 4.4's table."""
    with io.open(SPEC, encoding="utf-8") as handle:
        text = handle.read()
    section = text.split("### 4.4 專案屬性", 1)[1].split("### 4.5", 1)[0]
    return set(re.findall(r"`(cds-sync-[a-z-]+)`", section))


def in_code():
    """Every prefixed name cds/core/props.py defines."""
    return set(value for name, value in vars(props).items()
               if not name.startswith("_") and name != "PREFIX"
               and isinstance(value, str) and value.startswith(props.PREFIX))


def test_the_code_and_the_spec_name_the_same_properties():
    assert in_code() == documented()


def test_every_name_is_built_from_the_one_prefix():
    # This is the whole point of the module (SPEC D10): renaming the prefix
    # has to be one edit, not forty-nine.
    for name in in_code():
        assert name.startswith(props.PREFIX)


def test_the_odd_one_out_keeps_its_own_prefix():
    # cds-text-sync-multipleApps predates the rest and is written into every
    # project that has ever been synced. Folding it in would need a migration
    # pass over all of them; the exception is deliberate, so it is pinned.
    assert not props.MULTIPLE_APPS.startswith(props.PREFIX)
    assert props.MULTIPLE_APPS == "cds-text-sync-multipleApps"


def test_the_writable_table_is_the_spec_table_minus_the_one_a_person_sets():
    # cds/ide/config.py may read cds-sync-plc but never write it (SPEC 6.5),
    # so its table is every documented property except that one.
    from cds.ide import config
    assert set(config.PROPERTIES) == documented() - {props.PLC}
