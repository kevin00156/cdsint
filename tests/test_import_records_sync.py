# -*- coding: utf-8 -*-
"""An import leaves the sync cache describing what it imported.

The compare an import starts from saves the cache before anything is
applied, so an imported edit kept the entry from before the edit. The next
export read that as "edited on disk since the last sync": it refused to
write an IDE change made after the import, and the import after that wrote
the file back over the IDE, losing the change (SPEC 6.1).
"""
import pytest

from tests.sync_bench import Bench, folder, pou


@pytest.fixture
def bench(monkeypatch, tmp_path):
    made = Bench(monkeypatch, tmp_path, folder("A", pou("Foo")))
    assert made.export()["ok"]
    return made


def foo(bench):
    return bench.tree.get_children()[0].get_children()[0]


def test_an_ide_edit_after_an_import_is_exported(bench):
    bench.edit("A/Foo.st", u"x := 1;", u"x := 5;")
    assert bench.import_()["data"]["updated"] == 1
    foo(bench).textual_implementation.text = u"x := 5;\ny := 6;"

    result = bench.export()

    assert result["ok"] is True and result["data"]["pending_import"] == []
    assert u"y := 6;" in bench.read("A/Foo.st")


def test_so_the_next_import_does_not_undo_it(bench):
    bench.edit("A/Foo.st", u"x := 1;", u"x := 5;")
    bench.import_()
    foo(bench).textual_implementation.text = u"x := 5;\ny := 6;"
    bench.export()

    bench.import_()

    assert foo(bench).textual_implementation.text == u"x := 5;\ny := 6;"


def test_a_created_object_is_recorded_too(bench):
    bench.write("A/Bar.st", u"FUNCTION_BLOCK Bar\nVAR\nEND_VAR\n\n"
                            u"// === IMPLEMENTATION ===\nb := 1;")
    made = []
    folder_a = bench.tree.get_children()[0]

    def create_pou(name, kind):
        made.append(pou(name, u""))
        made[-1].owner, made[-1].parent = folder_a._children, folder_a
        folder_a._children.append(made[-1])
        return made[-1]
    folder_a.create_pou = create_pou
    folder_a.create_child = lambda name, kind: create_pou(name, kind)
    assert bench.import_()["data"]["created"] == 1
    made[0].textual_implementation.text = u"b := 2;"

    result = bench.export()

    assert result["data"]["pending_import"] == []
    assert u"b := 2;" in bench.read("A/Bar.st")
