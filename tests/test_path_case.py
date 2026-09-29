# -*- coding: utf-8 -*-
"""A sync-folder path is compared the way Windows compares it: ignoring case.

Renaming an object only in case (Foo to FOO) leaves its file on Windows
under the old case when export rewrites it. Every comparison of paths here
was case-sensitive, so the orphan sweep deleted the file export had just
written, the new-file scan offered it to import as a second object, and the
cache lost the entry the dirty-file guard reads. These run on any OS by
putting the old case on disk directly.
"""
from engine import change_detect, sync_cache
from engine.managers_base import ObjectManager
from engine.orphan_sweep import cleanup_orphaned_files


def old_case_on_disk(tmp_path):
    folder = tmp_path / "A"
    folder.mkdir()
    path = folder / "Foo.st"
    path.write_text(u"FUNCTION_BLOCK FOO\n", encoding="utf-8")
    mtime, size = sync_cache.file_signature(str(path))
    return path, {"ide_hash": "1", "disk_mtime": mtime, "disk_size": size}


def test_the_sweep_does_not_delete_the_file_of_an_object_renamed_in_case(tmp_path):
    path, entry = old_case_on_disk(tmp_path)
    sync_cache.save_sync_cache(str(tmp_path), {"A/Foo.st": entry})
    cached = sync_cache.load_sync_cache(str(tmp_path))["objects"]

    removed, kept = cleanup_orphaned_files(str(tmp_path), {"A/FOO.st"}, True,
                                           cached, {})

    assert path.exists() and removed == 0 and kept == []


def test_the_new_file_scan_does_not_offer_it_to_import(tmp_path):
    old_case_on_disk(tmp_path)

    assert change_detect.scan_new_disk_files(str(tmp_path),
                                             {"A/FOO.st": object()}) == []


def test_the_dirty_file_guard_still_finds_its_entry(tmp_path):
    path, entry = old_case_on_disk(tmp_path)
    entry["disk_size"] += 1   # the last sync saw something else there
    sync_cache.save_sync_cache(str(tmp_path), {"A/Foo.st": entry})
    context = {"cache_data": sync_cache.load_sync_cache(str(tmp_path))}

    assert ObjectManager()._disk_moved_since_sync("A/FOO.st", str(path),
                                                  context) is True
