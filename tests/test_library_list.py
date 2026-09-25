# -*- coding: utf-8 -*-
"""The Library Manager file: what a line means, and what a difference is (SPEC 6.9)."""
from cds.core import library_list as ll

UTIL = "Util, 3.5.19.0 (System)"
MEM = "CAA Memory, * (CAA Technical Workgroup)"


def test_render_sorts_by_kind_then_name_and_writes_system_as_comments():
    text = ll.render(
        [ll.entry("redirect", "Standard", "Standard, 3.5.18.0 (System)"),
         ll.entry("library", UTIL, options={"qualified_only": True}),
         ll.entry("placeholder", "MyUtil", "Util, 3.5.14.0 (System)"),
         ll.entry("library", MEM, options={"qualified_only": True, "namespace": "MEM"})],
        system=[("SM3_Basic", "SM3_Basic, 4.20.0.0 (CODESYS)", "resolved by device")])
    body = [l for l in text.splitlines() if l and not l.startswith("# cdsint")]
    assert body[0].startswith("library") and MEM in body[0]
    assert body[0].rstrip().endswith("qualified_only namespace=MEM")
    assert body[1].startswith("library") and UTIL in body[1]
    assert body[2] == "placeholder  MyUtil = Util, 3.5.14.0 (System)"
    assert body[3] == "redirect     Standard = Standard, 3.5.18.0 (System)"
    assert body[4].startswith("# system     SM3_Basic = SM3_Basic, 4.20.0.0 (CODESYS)")
    assert text.endswith("\n")


def test_parse_reads_back_what_render_wrote():
    entries = [ll.entry("library", UTIL, options={"qualified_only": True}),
               ll.entry("placeholder", "MyUtil", "Util, 3.5.14.0 (System)")]
    parsed, problems = ll.parse(ll.render(entries, system=[("X", "X, 1.0 (Y)", "by device")]))
    assert problems == []
    assert sorted(parsed, key=ll.key) == sorted(entries, key=ll.key)


def test_a_line_that_does_not_parse_is_named_by_number():
    _, problems = ll.parse("library Util 3.5 System\nfrobnicate x\n")
    assert problems[0].startswith("line 1:")
    assert problems[1].startswith("line 2:")


def test_an_unknown_option_is_a_problem():
    _, problems = ll.parse("library %s  shiny\n" % UTIL)
    assert problems and "shiny" in problems[0]


def test_the_same_entry_twice_is_a_problem():
    _, problems = ll.parse("library %s\nlibrary %s\n" % (UTIL, UTIL))
    assert problems and problems[0].startswith("line 2:")


def test_diff_by_name():
    have = [ll.entry("library", UTIL), ll.entry("library", "Old, 1.0 (X)"),
            ll.entry("redirect", "Standard", "Standard, 3.5.18.0 (System)")]
    wanted = [ll.entry("library", UTIL, options={"optional": True}),
              ll.entry("library", MEM),
              ll.entry("redirect", "Standard", "Standard, 3.5.14.0 (System)")]
    d = ll.diff(have, wanted)
    assert [e["name"] for e in d["remove"]] == ["Old, 1.0 (X)"]
    assert [e["name"] for e in d["add"]] == [MEM]
    assert sorted(new["name"] for _, new in d["change"]) == ["Standard", UTIL]


def test_same_ignores_comments_and_spacing():
    a = "library   %s   qualified_only\n" % UTIL
    b = "# a note\n\nlibrary %s qualified_only\n# system X = Y  whatever\n" % UTIL
    assert ll.same(a, b)


def test_same_is_false_when_the_disk_does_not_parse():
    assert not ll.same("library %s\n" % UTIL, "library broken\n")


def test_mismatches_names_what_did_not_land():
    after = [ll.entry("library", UTIL)]
    wanted = [ll.entry("library", UTIL, options={"optional": True}),
              ll.entry("library", MEM)]
    found = ll.mismatches(after, wanted)
    assert any(MEM in m for m in found) and any(UTIL in m for m in found)
