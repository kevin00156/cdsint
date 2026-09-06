# -*- coding: utf-8 -*-
"""Tests for the sync-cache primitives that decide whether work can be skipped.

The export side (codesys_managers) and the compare side
(codesys_compare_engine) read and write the SAME sync_cache.json under the
same keys. They used to derive 'disk_mtime' independently -- int(st.st_mtime)
on one side, os.path.getmtime() (a float) on the other -- so every entry
written by one was rejected by the other and both ran at a 0% hit rate on real
projects. These tests pin the shared representation down.
"""
import io
import json
import os

import pytest

from engine import (classify, codesys_compare_engine, codesys_managers,
                    codesys_utils, sync_cache)


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
        from_path = sync_cache.file_signature(sample_file)
        from_stat = sync_cache.file_signature(sample_file, os.stat(sample_file))
        assert from_path == from_stat

    def test_components_are_ints(self, utils, sample_file):
        """A float would make cache equality depend on repr() round-tripping
        the exact same value through JSON."""
        mtime, size = sync_cache.file_signature(sample_file)
        assert isinstance(mtime, int)
        assert isinstance(size, int)

    def test_survives_json_round_trip(self, utils, sample_file):
        sig = sync_cache.file_signature(sample_file)
        restored = json.loads(json.dumps({"disk_mtime": sig[0], "disk_size": sig[1]}))
        assert (restored["disk_mtime"], restored["disk_size"]) == sig

    def test_keeps_sub_second_resolution(self, utils, sample_file):
        """Truncating to whole seconds would silently miss an edit made in the
        same second as the cached stamp when the size happens to match."""
        os.utime(sample_file, (1_700_000_000.000, 1_700_000_000.000))
        first = sync_cache.file_signature(sample_file)
        os.utime(sample_file, (1_700_000_000.500, 1_700_000_000.500))
        second = sync_cache.file_signature(sample_file)
        assert first != second

    def test_detects_content_change(self, utils, sample_file):
        before = sync_cache.file_signature(sample_file)
        with open(sample_file, "a", encoding="utf-8") as handle:
            handle.write("// more\n")
        assert sync_cache.file_signature(sample_file) != before


class TestCrossSideAgreement:
    """The two sides must accept each other's cache entries."""

    def _export_side_entry(self, utils, file_path):
        """What ObjectManager._update_cache_entry stores."""
        mtime, size = sync_cache.file_signature(file_path, os.stat(file_path))
        return {"ide_hash": "A1B2C3D4", "disk_mtime": mtime, "disk_size": size}

    def _compare_side_accepts(self, utils, file_path, entry):
        """The predicate in find_all_changes."""
        mtime, size = sync_cache.file_signature(file_path)
        return entry.get("disk_mtime") == mtime and entry.get("disk_size") == size

    def _export_side_accepts(self, utils, file_path, entry):
        """The predicate in ObjectManager._try_cache_skip."""
        mtime, size = sync_cache.file_signature(file_path, os.stat(file_path))
        return entry.get("disk_mtime") == mtime and entry.get("disk_size") == size

    def test_compare_accepts_what_export_wrote(self, utils, sample_file):
        entry = self._export_side_entry(utils, sample_file)
        assert self._compare_side_accepts(utils, sample_file, entry)

    def test_export_accepts_what_compare_wrote(self, utils, sample_file):
        mtime, size = sync_cache.file_signature(sample_file)
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


class TestCachedClassification:
    """Every reader of the type cache indexes [2] without checking the length.

    That only holds because the cache is reshaped as it is loaded. Three
    readers used to ask `len(entry) > 2` for themselves, which is one
    question written three times and three chances to answer it differently.
    """

    def test_a_full_entry_is_returned_as_is(self, utils):
        assert sync_cache.cached_classification(["guid", True, "A/B.st"]) == (
            "guid", True, "A/B.st")

    def test_a_short_entry_is_padded(self, utils):
        """An older cache stored (eff_type, is_xml) with no path."""
        assert sync_cache.cached_classification(["guid", False]) == (
            "guid", False, None)

    def test_a_long_entry_is_cut(self, utils):
        assert sync_cache.cached_classification(["guid", False, "A.st", "extra"]) == (
            "guid", False, "A.st")

    def test_something_that_is_not_a_list_is_no_entry(self, utils):
        """A string would otherwise explode into one character per element."""
        assert sync_cache.cached_classification("guid") is None
        assert sync_cache.cached_classification(None) is None

    def test_load_reshapes_what_it_reads(self, utils, tmp_path):
        from engine.codesys_constants import PROFILE_HASH
        path = tmp_path / "sync_cache.json"
        path.write_text(json.dumps({
            "version": codesys_utils.CACHE_VERSION,
            "profile_hash": PROFILE_HASH,
            "objects": {}, "folders": {},
            "types": {"short": ["t", True], "full": ["t", False, "A.st"],
                      "junk": "not a list"},
        }), encoding="utf-8")
        types = sync_cache.load_sync_cache(str(tmp_path))["types"]
        assert types["short"] == ("t", True, None)
        assert types["full"] == ("t", False, "A.st")
        assert "junk" not in types


class TestManagerDispatch:
    """Which manager handles an object, asked once for both directions.

    There used to be two rules. Export looked for a dedicated manager first;
    import saw a ".xml" suffix and went straight to native, so a device --
    which has a ConfigManager of its own -- was handled by one manager on the
    way out and a different one on the way back.
    """

    def managers(self):
        return classify.create_import_managers(None)

    def test_a_kind_with_its_own_manager_gets_it_either_way(self):
        from engine.codesys_constants import TYPE_GUIDS
        mgrs = self.managers()
        device = TYPE_GUIDS["device"]
        assert classify.manager_for(mgrs, device, True) is mgrs[device]
        assert classify.manager_for(mgrs, device, False) is mgrs[device]

    def test_xml_without_a_dedicated_manager_goes_native(self):
        mgrs = self.managers()
        assert classify.manager_for(mgrs, "no-such-guid", True) is mgrs["native"]

    def test_text_without_a_dedicated_manager_goes_to_the_text_manager(self):
        mgrs = self.managers()
        assert classify.manager_for(mgrs, "no-such-guid", False) is mgrs["default"]

    def test_import_treats_an_xml_file_as_xml_backed(self):
        """Disk is the truth, so the suffix answers first (PRINCIPLES 5)."""
        assert codesys_compare_engine._is_xml_backed("A/B.device.xml", "guid")

    def test_import_treats_an_xml_kind_as_xml_backed_before_the_file_exists(self):
        from engine.codesys_constants import XML_TYPES
        any_xml_kind = sorted(XML_TYPES)[0]
        assert codesys_compare_engine._is_xml_backed("A/B", any_xml_kind)

    def test_a_plain_st_file_is_not_xml_backed(self):
        assert not codesys_compare_engine._is_xml_backed("A/B.st", "guid")


class TestHashContentPerKind:
    """What each flavour of native XML keeps, and what it throws away.

    Four booleans sniffed out of the text used to feed a nine-deep if/elif
    chain that mixed "which flavour is this" with "keep this line". These
    tests are about the first question and the second one separately, because
    that is what the chain made impossible to check.
    """

    def mgr(self, managers):
        return managers.NativeManager()

    def test_a_plain_document_drops_the_stamps_and_keeps_the_rest(self, managers):
        mgr = self.mgr(managers)
        body = '<Object>\n  <Body>content</Body>\n</Object>\n'
        stamped = ('<Object>\n'
                   '  <Single Name="Timestamp" Type="date">2026-08-13</Single>\n'
                   '  <Single Name="Guid" Type="System.Guid">abc</Single>\n'
                   '  <Body>content</Body>\n</Object>\n')
        assert mgr._hash_content(stamped) == mgr._hash_content(body)

    def test_a_plain_document_drops_churning_visualization_guids(self, managers):
        mgr = self.mgr(managers)
        body = '<Object>\n  <Body>content</Body>\n</Object>\n'
        with_visu = ('<Object>\n  <Object Guid="1" Type="visu"/>\n'
                     '  <Body>content</Body>\n</Object>\n')
        assert mgr._hash_content(with_visu) == mgr._hash_content(body)

    def test_a_device_drops_its_session_ids(self, managers):
        mgr = self.mgr(managers)
        plain = '<Device>\n  <Name>PLC</Name>\n</Device>\n'
        noisy = ('<Device>\n  <VQID>7</VQID>\n  <InstanceId>3</InstanceId>\n'
                 '  <Timestamp>2026-08-13</Timestamp>\n  <Name>PLC</Name>\n</Device>\n')
        assert mgr._hash_content(noisy) == mgr._hash_content(plain)

    def test_a_device_still_notices_a_real_change(self, managers):
        mgr = self.mgr(managers)
        one = '<Device>\n  <Name>PLC</Name>\n</Device>\n'
        two = '<Device>\n  <Name>OtherPLC</Name>\n</Device>\n'
        assert mgr._hash_content(one) != mgr._hash_content(two)

    def test_an_alarm_group_keeps_only_the_lines_that_identify_it(self, managers):
        mgr = self.mgr(managers)
        kept = '  <Single Name="Name" Type="string">AlarmGroup1</Single>\n'
        assert mgr._hash_content(kept + '  <Noise>a</Noise>\n') == \
            mgr._hash_content(kept + '  <Noise>b</Noise>\n')

    def test_a_textlist_is_not_read_as_an_alarm_group(self, managers):
        """'AlarmGroup' appears in a GlobalTextList too, and a text list keeps
        almost everything while an alarm group keeps almost nothing."""
        mgr = self.mgr(managers)
        head = '  <Single Name="Name" Type="string">GlobalTextList</Single>\n'
        assert mgr._hash_content(head + '  <Text>a</Text>\n') != \
            mgr._hash_content(head + '  <Text>b</Text>\n')

    def test_an_alarm_group_with_nothing_left_hashes_its_name(self, managers):
        """The filters can leave nothing at all. The hash then says where the
        content came from, not what it is -- preserved, not endorsed."""
        mgr = self.mgr(managers)
        volatile = '<AlarmGroup>\n  <Timestamp>2026-08-13</Timestamp>\n'
        assert mgr._hash_content(volatile, "one.xml") != \
            mgr._hash_content(volatile, "two.xml")

    def test_a_plain_document_with_nothing_left_does_not_hash_its_name(self, managers):
        """Only the alarm flavours fall back; an empty plain document is
        empty, and two empty ones are the same."""
        mgr = self.mgr(managers)
        assert mgr._hash_content("", "one.xml") == mgr._hash_content("", "two.xml")

    def test_content_that_cannot_be_hashed_raises(self, managers):
        """It used to return "", and NativeManager.export tests
        `old_hash and old_hash == new_hash` -- which "" makes false forever,
        so the object was reported "updated" on every export."""
        mgr = self.mgr(managers)
        with pytest.raises(Exception):
            mgr._hash_content(None)


class TestTheFilenameFallbackIsPinned:
    """All four special flavours hash the name when their filter leaves
    nothing. Only the plain one does not.

    That is the historic outcome and it is what contents_are_equal() leans
    on: it passes two deliberately different names, so an object whose whole
    content is volatile always compares as different rather than as
    accidentally identical. Preserved, not endorsed (ticket C ruling 3).

    The refactor that turned this into a table quietly narrowed it to two
    flavours and nothing failed, because the other two cannot be emptied by
    their own filters -- see the last test here. "Unreachable today" is not
    the same as "the rule says two", so the rule is pinned at four.
    """

    def flavours(self):
        from engine.codesys_managers import _XML_FLAVOURS, _PLAIN
        return _XML_FLAVOURS, _PLAIN

    def test_every_special_flavour_is_marked_as_falling_back(self):
        specials, _plain = self.flavours()
        assert len(specials) == 4
        assert all(f.name_is_the_fallback for f in specials)

    def test_the_plain_filter_is_not(self):
        """It throws away only what CODESYS rewrites, so a document it empties
        really is empty, and two empty documents are the same document."""
        _specials, plain = self.flavours()
        assert plain.name_is_the_fallback is False

    @pytest.mark.parametrize("content", [
        '<AlarmGroup>\n  <Timestamp>2026-08-13</Timestamp>\n',
        'Alarm Configuration\n  <Timestamp>2026-08-13</Timestamp>\n',
    ], ids=["alarm_group", "alarm_config"])
    def test_the_two_that_can_be_emptied_hash_their_name(self, managers, content):
        mgr = managers.NativeManager()
        assert mgr._hash_content(content, "one.xml") != \
            mgr._hash_content(content, "two.xml")

    @pytest.mark.parametrize("content", [
        '  <Single Name="Name" Type="string">GlobalTextList</Single>\n',
        '<Device>\n',
    ], ids=["textlist", "device"])
    def test_the_other_two_cannot_be_emptied_by_their_own_filter(self, content):
        """The line that says which flavour this is survives its own filter,
        so those two never reach the fallback. That is why narrowing the rule
        to two showed up in no test and in no exported byte."""
        from engine.codesys_managers import _xml_flavour
        flavour = _xml_flavour(content)
        assert [line for line in content.splitlines(True) if flavour.keep(line)]

    def test_an_alarm_group_keeps_a_nested_object_line(self, managers):
        """The alarm-group filter matches the object element anywhere in the
        line, not only at its start: the element is nested and arrives with
        its indentation. The plain filter uses startswith on purpose, because
        there it is throwing lines away rather than keeping them."""
        mgr = managers.NativeManager()
        one = '<AlarmGroup>\n        <Object Guid="1" Type="textlist"/>\n'
        two = '<AlarmGroup>\n        <Object Guid="2" Type="textlist"/>\n'
        assert mgr._hash_content(one, "x.xml") != mgr._hash_content(two, "x.xml")


class TestTheTempFileNeverSurvives:
    """NativeManager.export writes a .xml.tmp, hashes it, then renames it.

    _hash_content raises on content it cannot hash (that is the point of it
    no longer answering ""), and the hash happens after the temp file exists.
    Left behind, the .xml.tmp sits in the sync folder where the orphan sweep
    does not recognise it -- it is not .st or .xml -- and the next export
    writes a second one beside it.
    """

    class Node(object):
        def __init__(self, name="Thing"):
            self._name = name
            self.guid = "guid-" + name
            self.type = "t"
            self.parent = None

        def get_name(self):
            return self._name

        def get_children(self, recursive=False):
            return []

    class Project(object):
        """Writes the temp file the way export_native does."""

        def __init__(self, text=u"<Object/>\n"):
            self.text = text

        def export_native(self, objects, path, recursive=False):
            with io.open(path, "w", encoding="utf-8") as handle:
                handle.write(self.text)

    def context(self, tmp_path):
        return {"export_dir": str(tmp_path), "exported_paths": set(),
                "new_cache": {}, "cache_data": {}}

    def test_it_goes_when_the_hash_raises(self, managers, tmp_path, monkeypatch):
        mgr = managers.NativeManager(self.Project())

        def refuses(content_full, fallback_name=""):
            raise ValueError("cannot hash this")

        monkeypatch.setattr(mgr, "_hash_content", refuses)
        with pytest.raises(ValueError):
            mgr.export(self.Node(), "t", "Thing.xml", self.context(tmp_path))
        assert list(tmp_path.glob("*.tmp")) == []

    def test_it_goes_on_the_ordinary_path_too(self, managers, tmp_path):
        mgr = managers.NativeManager(self.Project())
        mgr.export(self.Node(), "t", "Thing.xml", self.context(tmp_path))
        assert list(tmp_path.glob("*.tmp")) == []
        assert (tmp_path / "Thing.xml").exists()
