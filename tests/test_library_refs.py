# -*- coding: utf-8 -*-
"""References in and out of a Library Manager (SPEC 6.9), on a fake one."""
from cds.core import library_list as ll
from engine import library_refs as lr
from tests.library_fakes import a_project_libman

STANDARD = ("placeholder Standard = Standard, * (System)\n"
            "redirect Standard = Standard, 3.5.18.0 (System)\n")


def names(libman):
    return [r.name for r in libman.references]


def test_read_splits_user_entries_from_system_ones():
    entries, system = lr.read(a_project_libman())
    kinds = sorted((e["kind"], e["name"]) for e in entries)
    assert kinds == [("library", "Util, 3.5.19.0 (System)"),
                     ("placeholder", "Standard"), ("redirect", "Standard")]
    assert sorted(s[0] for s in system) == ["SM3_Basic", "SysMem"]


def test_namespace_is_written_only_when_it_differs():
    lm = a_project_libman()
    entries, _ = lr.read(lm)
    util = [e for e in entries if e["kind"] == "library"][0]
    assert util["options"] == {"qualified_only": True}
    lm.references[-1].namespace = "U19"
    entries, _ = lr.read(lm)
    util = [e for e in entries if e["kind"] == "library"][0]
    assert util["options"] == {"qualified_only": True, "namespace": "U19"}


def test_a_library_with_no_default_namespace_defaults_to_its_title():
    # Measured: managed_library.default_namespace is None for Util and
    # ISysTypes2, whose namespace is their title.
    lm = a_project_libman()
    lm.add_library("ISysTypes2, 3.5.0.0 (System)")
    lm.add_library("CAA Memory, * (CAA Technical Workgroup)")
    options = dict((e["name"], e["options"]) for e in lr.read(lm)[0]
                   if e["kind"] == "library")
    assert all("namespace" not in o for o in options.values())


def test_render_ide_round_trips_through_parse():
    lm = a_project_libman()
    parsed, problems = ll.parse(lr.render_ide(lm))
    assert problems == []
    assert sorted(parsed, key=ll.key) == sorted(lr.read(lm)[0], key=ll.key)


def test_apply_adds_removes_and_redirects():
    lm = a_project_libman()
    wanted, _ = ll.parse(
        "library CAA Memory, * (CAA Technical Workgroup)  qualified_only\n"
        "placeholder Standard = Standard, * (System)\n"
        "redirect Standard = Standard, 3.5.14.0 (System)\n")
    assert lr.apply(lm, wanted) == []
    assert "Util, 3.5.19.0 (System)" not in names(lm)
    assert "CAA Memory, * (CAA Technical Workgroup)" in names(lm)
    standard = [r for r in lm.references if r.name == "#Standard"][0]
    assert standard.get_redirection() == "Standard, 3.5.14.0 (System)"


def test_an_unchanged_file_changes_nothing():
    lm = a_project_libman()
    before = lr.render_ide(lm)
    assert lr.apply(lm, lr.read(lm)[0]) == []
    assert lr.render_ide(lm) == before


def test_options_are_set_as_written():
    lm = a_project_libman()
    wanted, _ = ll.parse("library Util, 3.5.19.0 (System) optional namespace=U\n"
                         + STANDARD)
    assert lr.apply(lm, wanted) == []
    util = [r for r in lm.references if r.name.startswith("Util")][0]
    assert (util.qualified_only, util.optional, util.namespace) == (False, True, "U")


def test_system_references_are_never_removed():
    lm = a_project_libman()
    assert lr.apply(lm, []) == []
    assert "#SM3_Basic" in names(lm) and "#SysMem" in names(lm)


def test_a_library_that_is_not_installed_is_taken_back_and_named():
    lm = a_project_libman()
    wanted, _ = ll.parse("library Util, 3.5.19.0 (System) qualified_only\n"
                         "library NoSuchLib, 1.0.0.0 (Nobody)\n" + STANDARD)
    problems = lr.apply(lm, wanted)
    assert problems == ["library NoSuchLib, 1.0.0.0 (Nobody): not installed "
                        "on this machine"]
    assert "NoSuchLib, 1.0.0.0 (Nobody)" not in names(lm)


def test_on_4_0_the_refusal_is_the_same_problem():
    lm = a_project_libman(strict=True)
    wanted, _ = ll.parse("library NoSuchLib, 1.0.0.0 (Nobody)\n" + STANDARD)
    problems = lr.apply(lm, wanted)
    assert any("NoSuchLib" in p and "not installed" in p for p in problems)


def test_a_redirect_without_its_placeholder_is_named():
    lm = a_project_libman()
    wanted, _ = ll.parse("library Util, 3.5.19.0 (System) qualified_only\n"
                         + STANDARD + "redirect Ghost = Ghost, 1.0 (X)\n")
    problems = lr.apply(lm, wanted)
    assert any(p.startswith("redirect Ghost") for p in problems)


def test_a_placeholder_that_resolved_elsewhere_is_a_problem():
    lm = a_project_libman()
    wanted, _ = ll.parse("library Util, 3.5.19.0 (System) qualified_only\n"
                         "placeholder MyUtil = Util, 3.5.14.0 (System)\n"
                         + STANDARD)
    add = lm.add_placeholder

    def resolving_elsewhere(name, default):
        add(name, default)
        lm.references[-1]._effective = "Util, 3.5.1.0 (System)"
    lm.add_placeholder = resolving_elsewhere
    problems = lr.apply(lm, wanted)
    assert any("MyUtil" in p and "3.5.1.0" in p for p in problems)
