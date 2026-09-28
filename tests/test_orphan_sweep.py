# -*- coding: utf-8 -*-
"""The orphan sweep deletes only what the last sync left and nobody touched.

"No object claims this file" was the whole test, so --delete-orphans (or
auto_delete_orphans, without asking) deleted a POU somebody had just written
for import to create, and an edit made on disk to a file whose object was
renamed in the IDE meanwhile. Disk is the source of truth (PRINCIPLES 5): an
orphan now also needs a cache entry its file still matches.
"""
import pytest

from engine import entry_export
from tests.sync_bench import Bench, folder, pou

NEW_FB = u"FUNCTION_BLOCK NewFb\nVAR\nEND_VAR\n\n// === IMPLEMENTATION ===\ny := 2;"


@pytest.fixture
def bench(monkeypatch, tmp_path):
    made = Bench(monkeypatch, tmp_path, folder("A", pou("Foo")))
    assert made.export()["ok"]
    return made


def foo(bench):
    return bench.tree.get_children()[0].get_children()[0]


def test_a_file_written_for_import_is_not_deleted(bench):
    bench.write("A/NewFb.st", NEW_FB)

    result = bench.export(auto_delete_orphans=True)

    assert bench.read("A/NewFb.st") == NEW_FB
    assert result["data"]["pending_import"] == ["A/NewFb.st"]
    assert result["ok"] is False


def test_an_edit_to_a_file_whose_object_was_renamed_is_not_deleted(bench):
    bench.edit("A/Foo.st", u"x := 1;", u"x := 1; // precious")
    foo(bench)._name = "Foo2"

    result = bench.export(auto_delete_orphans=True)

    assert u"precious" in bench.read("A/Foo.st")
    assert result["data"]["pending_import"] == ["A/Foo.st"]
    assert result["data"]["removed"] == 0


def test_the_file_of_a_renamed_object_nobody_touched_is_still_swept(bench):
    foo(bench)._name = "Foo2"

    result = bench.export(auto_delete_orphans=True)

    assert bench.files() == ["A/Foo2.st"]
    assert result["data"]["removed"] == 1 and result["ok"] is True


def test_an_orphan_somebody_declined_to_delete_is_offered_again(bench):
    foo(bench)._name = "Foo2"
    bench.answer = False
    first = bench.export()
    bench.answer = True

    second = bench.export()

    assert first["data"]["removed"] == 0 and first["ok"] is True
    assert second["data"]["removed"] == 1
    assert bench.files() == ["A/Foo2.st"]


def test_a_folder_with_no_cache_has_no_orphans(bench):
    bench.sync.joinpath("sync_cache.json").unlink()
    foo(bench)._name = "Foo2"

    result = bench.export(auto_delete_orphans=True)

    assert bench.files() == ["A/Foo.st", "A/Foo2.st"]
    assert result["data"]["pending_import"] == ["A/Foo.st"]


def test_a_compare_in_between_does_not_turn_an_orphan_into_new_work(bench):
    # Compare rewrites the cache from what it walked. The orphan's file has
    # no object, so its entry used to be dropped, and the export after it
    # kept the file as unknown and reported it as waiting for import.
    foo(bench)._name = "Foo2"
    bench.compare()

    result = bench.export(auto_delete_orphans=True)

    assert bench.files() == ["A/Foo2.st"]
    assert result["data"]["pending_import"] == []


def test_an_edit_to_the_file_of_an_unreadable_object_survives_it(
        monkeypatch, tmp_path):
    # The sweep skipped by an object it could not classify emptied its kept
    # list with the deletions, so the edited file lost its cache entry, read
    # as never synced once the object could be read again, and that export
    # wrote the IDE's text over the edit.
    bench = Bench(monkeypatch, tmp_path, folder("A", pou("Foo"), pou("Bar")))
    assert bench.export()["ok"]
    bench.edit("A/Bar.st", u"x := 1;", u"x := 1; // precious")
    resolve = entry_export.resolve_object

    def unreadable_bar(obj, *args):
        if obj.get_name() == "Bar":
            raise IOError("the plugin for Bar is missing")
        return resolve(obj, *args)

    monkeypatch.setattr(entry_export, "resolve_object", unreadable_bar)
    skipped = bench.export(auto_delete_orphans=True)
    monkeypatch.setattr(entry_export, "resolve_object", resolve)
    again = bench.export()

    assert skipped["data"]["pending_import"] == ["A/Bar.st"]
    assert u"precious" in bench.read("A/Bar.st")
    assert again["data"]["pending_import"] == ["A/Bar.st"]
