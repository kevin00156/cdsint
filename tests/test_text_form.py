# -*- coding: utf-8 -*-
"""A file that differs from the IDE only in form is not a difference.

Import strips every section it reads, so a file saved with CRLF line
endings or an extra final newline goes in fine. Compare and export then
held that same file against the IDE byte for byte, and it stayed "Modified"
after every import, for ever. Both now compare through st_text.canonical_st.
"""
import pytest

from engine import st_text
from tests.sync_bench import Bench, folder, pou


@pytest.fixture
def imported(monkeypatch, tmp_path):
    """Foo edited in an editor that writes CRLF and a final newline, then
    imported."""
    bench = Bench(monkeypatch, tmp_path, folder("A", pou("Foo")))
    assert bench.export()["ok"]
    text = bench.read("A/Foo.st").replace(u"x := 1;", u"x := 5;  ")
    bench.write("A/Foo.st", text.replace(u"\n", u"\r\n") + u"\r\n\r\n")
    assert bench.import_()["data"]["updated"] == 1
    return bench


def test_compare_finds_nothing_left_to_import(imported):
    assert imported.compare()["different"] == []


def test_a_second_import_has_nothing_to_do(imported):
    assert imported.import_()["data"]["identical"] == 1


def test_export_leaves_the_file_as_the_editor_wrote_it(imported):
    before = imported.read("A/Foo.st")

    result = imported.export()

    assert imported.read("A/Foo.st") == before
    assert result["ok"] is True and result["data"]["pending_import"] == []


@pytest.mark.parametrize("variant", [
    u"FUNCTION_BLOCK Foo\r\nVAR\r\nEND_VAR\r\n\r\n// === IMPLEMENTATION ===\r\nx := 1;\r\n",
    u"FUNCTION_BLOCK Foo   \nVAR\nEND_VAR\n\n\n\n// === IMPLEMENTATION ===\n\n  x := 1;\n\n",
])
def test_form_is_all_the_normaliser_drops(variant):
    plain = u"FUNCTION_BLOCK Foo\nVAR\nEND_VAR\n\n// === IMPLEMENTATION ===\nx := 1;"
    assert st_text.canonical_st(variant) == st_text.canonical_st(plain)
    assert st_text.canonical_st(variant.replace(u"x := 1", u"x := 2")) != \
        st_text.canonical_st(plain)
