# -*- coding: utf-8 -*-
"""An EtherCAT device's settings file (SPEC 6.10)."""
from cds.core import device_text as dt

IDENT = "65|766_0001000000000001|Revision=16#00000001"
VALUES = [("c1/1610633216", "1000", "DC sync0 cycletime"),
          ("c1/1627394048/Value", "6", "Op mode")]
MAPS = [("c1/33554435", "Application.GVL_Axis.aDriveErrorCodes[1]",
         "Error Code, %IW5")]


def test_render_then_parse():
    doc, problems = dt.parse(dt.render(IDENT, VALUES, MAPS))
    assert problems == []
    assert doc == {"ident": IDENT,
                   "values": {"c1/1610633216": "1000", "c1/1627394048/Value": "6"},
                   "maps": {"c1/33554435": "Application.GVL_Axis.aDriveErrorCodes[1]"}}


def test_render_puts_the_names_in_comments_and_sorts():
    text = dt.render(IDENT, list(reversed(VALUES)), MAPS)
    lines = [l for l in text.splitlines() if l and not l.startswith("#")]
    assert lines[0] == "device  " + IDENT
    assert lines[1].startswith("c1/1610633216 = 1000") and lines[1].endswith("# DC sync0 cycletime")
    assert lines[3].startswith("map c1/33554435 = Application.GVL_Axis")


def test_a_value_may_hold_a_hash_or_equals_and_keeps_them():
    doc, problems = dt.parse("device  %s\nc1/5 = 'a = b'    # note\nc1/6 = x#1\n" % IDENT)
    assert problems == []
    assert doc["values"] == {"c1/5": "'a = b'", "c1/6": "x#1"}


def test_an_empty_value_is_a_value():
    doc, problems = dt.parse("device  %s\nc1/7 = \n" % IDENT)
    assert problems == [] and doc["values"] == {"c1/7": ""}


def test_bad_lines_are_named():
    _, problems = dt.parse("device  %s\nnonsense\nc1/1 = 2\nc1/1 = 3\n" % IDENT)
    assert problems[0].startswith("line 2:")
    assert problems[1].startswith("line 4:")


def test_the_device_line_is_required_once():
    _, problems = dt.parse("c1/1 = 2\n")
    assert any("device" in p for p in problems)
    _, problems = dt.parse("device  a\ndevice  b\n")
    assert problems and problems[0].startswith("line 2:")


def test_diff_writes_what_differs_and_unmaps_what_is_gone():
    have, _ = dt.parse(dt.render(IDENT, VALUES, MAPS))
    wanted, _ = dt.parse(dt.render(IDENT, [("c1/1610633216", "2000", ""),
                                           ("c1/1627394048/Value", "6", "")], []))
    assert dt.diff(have, wanted) == {"values": {"c1/1610633216": "2000"},
                                     "maps": {"c1/33554435": ""}}


def test_same_ignores_comments_and_spacing():
    a = dt.render(IDENT, VALUES, MAPS)
    b = ("device %s\n# hello\nc1/1627394048/Value=6\nc1/1610633216  =  1000\n"
         "map c1/33554435 = Application.GVL_Axis.aDriveErrorCodes[1]\n" % IDENT)
    assert dt.same(a, b)
    assert not dt.same(a, b.replace("1000", "2000"))


def test_mismatches_name_the_key():
    after, _ = dt.parse(dt.render(IDENT, [("c1/1610633216", "2000", "")], []))
    wanted, _ = dt.parse(dt.render(IDENT, [("c1/1610633216", "4000", "")], []))
    found = dt.mismatches(after, wanted)
    assert found == ["c1/1610633216: written 4000, the IDE has 2000"]


def test_a_value_line_left_out_is_not_managed_but_a_map_left_out_is_unmapped():
    after, _ = dt.parse(dt.render(IDENT, VALUES, MAPS))
    wanted, _ = dt.parse(dt.render(IDENT, [("c1/1610633216", "1000", "")], MAPS))
    assert dt.mismatches(after, wanted) == []
    wanted_no_map, _ = dt.parse(dt.render(IDENT, VALUES, []))
    assert dt.mismatches(after, wanted_no_map) == [
        "map c1/33554435: written (nothing), the IDE has "
        "Application.GVL_Axis.aDriveErrorCodes[1]"]
