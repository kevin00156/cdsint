# -*- coding: utf-8 -*-
"""Tests for tools/release_notes.py: what the release job publishes, or refuses."""
import pytest

from engine.codesys_constants import SCRIPT_VERSION
from tools import release_notes

CHANGELOG = u"""# Changelog

---

### {v} (2026-10-01) — the one being released

- **A change.** Said in full.

### 0.0.1 (2026-09-22) — the one before

- Something older.

---
"""


def test_the_section_under_the_version_heading():
    text = CHANGELOG.format(v=SCRIPT_VERSION)
    assert release_notes.notes("v" + SCRIPT_VERSION, text) == (
        "- **A change.** Said in full.\n")


def test_the_last_section_stops_at_the_rule():
    assert release_notes.section(CHANGELOG.format(v="9.9.9"), "0.0.1") == (
        "- Something older.\n")


def test_a_tag_that_is_not_the_version_is_refused():
    with pytest.raises(ValueError):
        release_notes.notes("v99.0.0", CHANGELOG.format(v="99.0.0"))


def test_an_undated_section_is_refused():
    text = CHANGELOG.replace("### {v} (2026-10-01)",
                             "### Unreleased ({v})").format(v=SCRIPT_VERSION)
    with pytest.raises(ValueError):
        release_notes.notes("v" + SCRIPT_VERSION, text)
