# -*- coding: utf-8 -*-
"""The build record beside the project (SPEC 6.9, Build)."""
from cds.core import build_record as br


def test_the_record_sits_beside_the_project(tmp_path):
    p = str(tmp_path / "Line.project")
    assert br.path_for(p) == str(tmp_path / "Line.cdsint-build.json")


def test_a_missing_or_broken_record_reads_as_empty(tmp_path):
    path = str(tmp_path / "x.cdsint-build.json")
    assert br.read(path) == {}
    with open(path, "w") as f:
        f.write("{not json")
    assert br.read(path) == {}


def test_a_record_that_is_not_an_object_reads_as_empty(tmp_path):
    path = str(tmp_path / "x.cdsint-build.json")
    with open(path, "w") as f:
        f.write("[1, 2]")
    assert br.read(path) == {}


def test_write_then_read(tmp_path):
    path = str(tmp_path / "x.cdsint-build.json")
    digest = br.digest(u"library Util, 3.5.19.0 (System)\n")
    br.write(path, {"Application": digest})
    assert br.read(path) == {"Application": digest}


def test_digest_changes_with_the_text():
    assert br.digest(u"a") != br.digest(u"b")
    assert len(br.digest(u"a")) == 8
