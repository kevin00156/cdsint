# -*- coding: utf-8 -*-
"""Tests for the sync-cache primitives that decide whether work can be skipped.

The export side (codesys_managers) and the compare side
(codesys_compare_engine) read and write the SAME sync_cache.json under the
same keys. They used to derive 'disk_mtime' independently -- int(st.st_mtime)
on one side, os.path.getmtime() (a float) on the other -- so every entry
written by one was rejected by the other and both ran at a 0% hit rate on real
projects. These tests pin the shared representation down.
"""
import json
import os

import pytest

from engine import codesys_compare_engine, codesys_managers, codesys_utils


@pytest.fixture(scope="module")
def utils():
    return codesys_utils


@pytest.fixture(scope="module")
def managers(utils):
    return codesys_managers


@pytest.fixture
def sample_file(tmp_path):
    path = tmp_path / "Sample.st"
    path.write_text("FUNCTION_BLOCK FB\nEND_FUNCTION_BLOCK\n", encoding="utf-8")
    return str(path)


class TestFileSignature:
    def test_path_and_stat_agree(self, utils, sample_file):
        """Passing a pre-fetched stat must not change the answer -- the export
        path reuses a stat it already has, the compare path does not."""
        from_path = utils.file_signature(sample_file)
        from_stat = utils.file_signature(sample_file, os.stat(sample_file))
        assert from_path == from_stat

    def test_components_are_ints(self, utils, sample_file):
        """A float would make cache equality depend on repr() round-tripping
        the exact same value through JSON."""
        mtime, size = utils.file_signature(sample_file)
        assert isinstance(mtime, int)
        assert isinstance(size, int)

    def test_survives_json_round_trip(self, utils, sample_file):
        sig = utils.file_signature(sample_file)
        restored = json.loads(json.dumps({"disk_mtime": sig[0], "disk_size": sig[1]}))
        assert (restored["disk_mtime"], restored["disk_size"]) == sig

    def test_keeps_sub_second_resolution(self, utils, sample_file):
        """Truncating to whole seconds would silently miss an edit made in the
        same second as the cached stamp when the size happens to match."""
        os.utime(sample_file, (1_700_000_000.000, 1_700_000_000.000))
        first = utils.file_signature(sample_file)
        os.utime(sample_file, (1_700_000_000.500, 1_700_000_000.500))
        second = utils.file_signature(sample_file)
        assert first != second

    def test_detects_content_change(self, utils, sample_file):
        before = utils.file_signature(sample_file)
        with open(sample_file, "a", encoding="utf-8") as handle:
            handle.write("// more\n")
        assert utils.file_signature(sample_file) != before


class TestCrossSideAgreement:
    """The two sides must accept each other's cache entries."""

    def _export_side_entry(self, utils, file_path):
        """What ObjectManager._update_cache_entry stores."""
        mtime, size = utils.file_signature(file_path, os.stat(file_path))
        return {"ide_hash": "A1B2C3D4", "disk_mtime": mtime, "disk_size": size}

    def _compare_side_accepts(self, utils, file_path, entry):
        """The predicate in find_all_changes."""
        mtime, size = utils.file_signature(file_path)
        return entry.get("disk_mtime") == mtime and entry.get("disk_size") == size

    def _export_side_accepts(self, utils, file_path, entry):
        """The predicate in ObjectManager._try_cache_skip."""
        mtime, size = utils.file_signature(file_path, os.stat(file_path))
        return entry.get("disk_mtime") == mtime and entry.get("disk_size") == size

    def test_compare_accepts_what_export_wrote(self, utils, sample_file):
        entry = self._export_side_entry(utils, sample_file)
        assert self._compare_side_accepts(utils, sample_file, entry)

    def test_export_accepts_what_compare_wrote(self, utils, sample_file):
        mtime, size = utils.file_signature(sample_file)
        entry = {"ide_hash": "A1B2C3D4", "disk_mtime": mtime, "disk_size": size}
        assert self._export_side_accepts(utils, sample_file, entry)

    def test_both_reject_after_a_real_edit(self, utils, sample_file):
        entry = self._export_side_entry(utils, sample_file)
        os.utime(sample_file, (1_700_000_000, 1_700_000_000))
        assert not self._compare_side_accepts(utils, sample_file, entry)
        assert not self._export_side_accepts(utils, sample_file, entry)

    def test_survives_a_full_json_round_trip(self, utils, sample_file, tmp_path):
        """The realistic path: export writes the cache, compare reads it back."""
        cache_path = tmp_path / "sync_cache.json"
        entry = self._export_side_entry(utils, sample_file)
        cache_path.write_text(json.dumps({"objects": {"Sample.st": entry}}),
                              encoding="utf-8")
        reloaded = json.loads(cache_path.read_text(encoding="utf-8"))
        assert self._compare_side_accepts(
            utils, sample_file, reloaded["objects"]["Sample.st"])


class TestNativeHashContent:
    """_hash_file was split into _hash_content so the compare engine can hash
    XML it already holds in memory instead of writing it back to a temp file."""

    XML = ('<?xml version="1.0"?>\n'
           '<Project>\n'
           '  <Single Name="Name" Type="string">Thing</Single>\n'
           '  <Body>content</Body>\n'
           '</Project>\n')

    def test_file_and_content_hashes_match(self, managers, tmp_path):
        path = tmp_path / "Thing.pou_xml.xml"
        # write_bytes, not write_text: the engine reads and writes exclusively
        # through codecs.open(), which never translates line endings, so the
        # bytes on disk must match the string byte for byte for this identity
        # to mean anything.
        path.write_bytes(self.XML.encode("utf-8"))
        mgr = managers.NativeManager()
        assert mgr._hash_file(str(path)) == mgr._hash_content(self.XML)

    def test_differing_content_differs(self, managers):
        mgr = managers.NativeManager()
        other = self.XML.replace("content", "changed")
        assert mgr._hash_content(self.XML) != mgr._hash_content(other)

    def test_timestamp_lines_are_ignored(self, managers):
        """The whole point of the filtering: CODESYS rewrites these on every
        export, so they must not count as a change."""
        mgr = managers.NativeManager()
        stamped = self.XML.replace(
            "  <Body>content</Body>\n",
            '  <Single Name="Timestamp" Type="date">2026-08-13</Single>\n'
            "  <Body>content</Body>\n")
        assert mgr._hash_content(stamped) == mgr._hash_content(self.XML)

    def test_missing_file_returns_empty(self, managers, tmp_path):
        mgr = managers.NativeManager()
        assert mgr._hash_file(str(tmp_path / "nope.xml")) == ""
