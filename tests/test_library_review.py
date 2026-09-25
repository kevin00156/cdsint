# -*- coding: utf-8 -*-
"""What the whole-branch review of SPEC 6.9 found, each pinned by a test."""
import io

from cds.core import build_record
from cds.core import library_list as ll
from engine import ide_hash, import_items, move_detect, unhandled
from engine import library_refs as lr
from engine.codesys_constants import TYPE_GUIDS
from engine.managers_library import LibraryManager
from tests.fakes import Node
from tests.library_fakes import a_project_libman

LM = TYPE_GUIDS["library_manager"]
STANDARD = ("placeholder Standard = Standard, * (System)\n"
            "redirect Standard = Standard, 3.5.18.0 (System)\n")


def test_the_quick_hash_sees_a_library_removed_in_the_ide():
    # Without one, the folder hash left the Library Manager out and a second
    # compare called an IDE-side change "unchanged".
    lm = a_project_libman()
    before = ide_hash.get_quick_ide_hash(lm, False)
    lm.remove_library("Util, 3.5.19.0 (System)")
    after = ide_hash.get_quick_ide_hash(lm, False)
    assert before and after and before != after


def test_spacing_inside_a_name_is_not_a_difference():
    assert ll.same("library Util, 3.5.19.0 (System)\n",
                   "library Util,  3.5.19.0  (System)\n")


def test_case_in_a_name_is_not_a_difference():
    assert ll.same("library Util, 3.5.19.0 (System)\n",
                   "library util, 3.5.19.0 (System)\n")


def test_a_respaced_name_does_not_remove_and_re_add_the_library():
    lm = a_project_libman()
    util = [r for r in lm.references if r.name.startswith("Util")][0]
    util.optional = True
    wanted, _ = ll.parse("library Util,  3.5.19.0 (System) qualified_only optional\n"
                         + STANDARD)
    assert lr.apply(lm, wanted) == []
    assert [r for r in lm.references if r.name.startswith("Util")] == [util]


def test_one_call_that_raises_is_named_and_the_rest_still_happens():
    lm = a_project_libman()

    def refusing(name, default):
        raise Exception("placeholder refused")
    lm.add_placeholder = refusing
    wanted, _ = ll.parse("library CAA Memory, * (CAA Technical Workgroup) qualified_only\n"
                         "placeholder MyUtil = Util, 3.5.14.0 (System)\n" + STANDARD)
    problems = lr.apply(lm, wanted)
    assert any(p.startswith("placeholder MyUtil:") and "refused" in p
               for p in problems)
    names = [r.name for r in lm.references]
    assert "CAA Memory, * (CAA Technical Workgroup)" in names
    assert "Util, 3.5.19.0 (System)" not in names


def test_a_legacy_library_manager_xml_is_refused_not_merged(tmp_path):
    rel = "Dev/Application/Library Manager.library_manager.xml"
    path = tmp_path / "Dev" / "Application"
    path.mkdir(parents=True)
    (path / "Library Manager.library_manager.xml").write_text(u"<x/>")
    item = {"path": rel, "name": "Library Manager", "type_guid": ""}
    tally = import_items._Tally()
    unhandled.start()
    batches, st_files = import_items._sort_items(
        [item], str(tmp_path), None, set(), tally)
    assert batches == {} and st_files == [] and tally.failed == 1
    assert [r["name"] for r in unhandled.records()] == [rel]
    assert "Run export first" in unhandled.records()[0]["reason"]


class Project(object):
    def __init__(self, path):
        self.path = path


def test_an_import_that_changed_libraries_makes_the_next_build_clean(tmp_path):
    # A person's own IDE build is not in the record; after import puts the
    # list back to the recorded one, only forgetting the record forces a
    # clean (research 5.2).
    project = str(tmp_path / "Line.project")
    record = build_record.path_for(project)
    build_record.write(record, {"Application": "ABCD1234", "Other": "1"})
    lm = a_project_libman()
    Node("Application", TYPE_GUIDS["application"], children=[lm])
    f = tmp_path / "Library Manager.libraries"
    with io.open(str(f), "w", encoding="utf-8") as out:
        out.write(u"library CAA Memory, * (CAA Technical Workgroup) qualified_only\n"
                  + STANDARD)
    assert LibraryManager(Project(project)).update(lm, str(f))
    assert build_record.read(record) == {"Other": "1"}


def test_library_manager_files_are_never_paired_as_moves():
    ide = [{"path": "A/App1/Library Manager.libraries", "name": "Library Manager"}]
    disk = [{"path": "A/App0/Library Manager.libraries", "name": "Library Manager"}]
    moved, new_in_ide, new_on_disk = move_detect.detect_moved_files(ide, disk)
    assert moved == [] and new_in_ide == ide and new_on_disk == disk
