# -*- coding: utf-8 -*-
"""The Library Manager as a text kind, through the existing plumbing (SPEC 6.9)."""
import io

import pytest

from engine import (classify, content_compare, import_items, object_paths,
                    sync_dir)
from engine.codesys_constants import (TYPE_GUIDS, XML_TYPES,
                                      kind_allows_import)
from engine.managers_library import LibraryManager
from tests.fakes import Node
from tests.library_fakes import a_project_libman

LM = TYPE_GUIDS["library_manager"]


def write(path, text):
    with io.open(str(path), "w", encoding="utf-8") as f:
        f.write(text)


def test_it_is_an_importable_text_kind_now():
    assert LM not in XML_TYPES
    assert kind_allows_import("library_manager")


def test_its_file_is_named_libraries():
    lm = Node("Library Manager", LM)
    Node("Application", TYPE_GUIDS["application"], children=[lm])
    path = object_paths.build_expected_path(lm, LM, False, obj_guid="g")
    assert path.endswith("Library Manager.libraries")


def test_the_sync_walk_sees_it(tmp_path):
    write(tmp_path / "Library Manager.libraries", u"library X, 1.0 (Y)\n")
    found = [rel for rel, _ in sync_dir.sync_files(str(tmp_path))]
    assert found == ["Library Manager.libraries"]


def test_it_has_its_own_manager():
    managers = classify.create_import_managers(project=None)
    assert isinstance(classify.manager_for(managers, LM, False), LibraryManager)


def test_it_is_written_whether_or_not_export_xml_is_on():
    lm = Node("Library Manager", LM)
    Node("Application", TYPE_GUIDS["application"], children=[lm])
    decided = classify.resolve_object(lm, "guid-Lib", {}, export_xml=False,
                                      project=None)
    assert decided.skip_reason is None
    assert decided.rel_path.endswith(".libraries")


def test_compare_reads_the_ide_through_the_api():
    lm = a_project_libman()
    content, attrs = content_compare.get_ide_content(lm, False, {}, None)
    assert "library      Util, 3.5.19.0 (System)" in content and attrs == {}


def test_compare_ignores_comments_and_spacing():
    ide = u"library Util, 3.5.19.0 (System) qualified_only\n"
    disk = u"# note\nlibrary   Util, 3.5.19.0 (System)   qualified_only\n"
    assert content_compare.contents_are_equal(
        ide, disk, False, "A/Library Manager.libraries")
    assert not content_compare.contents_are_equal(
        ide, u"library Util, 3.5.19.0 (System)\n", False,
        "A/Library Manager.libraries")


def test_update_applies_and_says_it_changed(tmp_path):
    lm = a_project_libman()
    f = tmp_path / "Library Manager.libraries"
    write(f, u"placeholder Standard = Standard, * (System)\n"
             u"redirect Standard = Standard, 3.5.18.0 (System)\n")
    assert LibraryManager(None).update(lm, str(f))
    assert "Util, 3.5.19.0 (System)" not in [r.name for r in lm.references]


def test_update_refuses_a_file_that_does_not_parse_and_changes_nothing(tmp_path):
    lm = a_project_libman()
    before = [r.name for r in lm.references]
    f = tmp_path / "Library Manager.libraries"
    write(f, u"library broken\n")
    with pytest.raises(RuntimeError) as err:
        LibraryManager(None).update(lm, str(f))
    assert "line 1" in str(err.value)
    assert [r.name for r in lm.references] == before


def test_update_names_what_did_not_land(tmp_path):
    lm = a_project_libman()
    f = tmp_path / "Library Manager.libraries"
    write(f, u"library NoSuchLib, 1.0.0.0 (Nobody)\n")
    with pytest.raises(RuntimeError) as err:
        LibraryManager(None).update(lm, str(f))
    assert "NoSuchLib" in str(err.value)


def test_create_is_refused_with_a_reason():
    with pytest.raises(RuntimeError) as err:
        LibraryManager(None).create(None, "Library Manager", "x.libraries", LM)
    assert "does not create" in str(err.value)


def test_a_file_with_no_library_manager_is_not_created_as_something_else(tmp_path):
    f = tmp_path / "Library Manager.libraries"
    write(f, u"library Util, 3.5.19.0 (System)\n")
    rel = "Dev/Plc Logic/App/Library Manager.libraries"
    with pytest.raises(RuntimeError) as err:
        import_items._create_st({"path": rel}, rel, str(f), {}, {}, {}, None,
                                import_items._Tally())
    assert "does not create" in str(err.value)


class Removable(Node):
    removed = False

    def remove(self):
        self.removed = True


def test_a_library_manager_whose_file_is_gone_is_never_deleted(tmp_path):
    lm = Removable("Library Manager", LM)
    item = {"is_orphan": True, "obj": lm, "name": "Library Manager",
            "type_guid": LM, "path": "A/Library Manager.libraries"}
    tally = import_items._Tally()
    import_items._sort_items([item], str(tmp_path), None, set(), tally)
    assert not lm.removed and tally.deleted == 0


def test_a_libraries_file_goes_to_the_text_pass(tmp_path):
    write(tmp_path / "Library Manager.libraries", u"")
    item = {"path": "Library Manager.libraries", "name": "Library Manager",
            "type_guid": LM}
    batches, st_files = import_items._sort_items(
        [item], str(tmp_path), None, set(), import_items._Tally())
    assert st_files == [item] and batches == {}


def export_context(tmp_path, rel):
    # The cache says the file looked different at the last sync, which is
    # what makes an ordinary text kind refuse to overwrite it (SPEC 6.1).
    return {"export_dir": str(tmp_path), "exported_paths": set(),
            "new_cache": {}, "cache_data": {"objects": {
                rel: {"disk_mtime": 1, "disk_size": 1, "ide_hash": "x"}}}}


def test_export_rewrites_a_file_that_only_differs_in_form(tmp_path):
    # Measured: after importing a hand-added line at the end of the file,
    # the export refused to write the sorted form ("edited on disk since the
    # last sync"), and verify stopped. Same entries means nothing to lose.
    lm = a_project_libman()
    rel = "Library Manager.libraries"
    entries_in_other_order = (u"redirect Standard = Standard, 3.5.18.0 (System)\r\n"
                              u"placeholder Standard = Standard, * (System)\r\n"
                              u"library Util, 3.5.19.0 (System) qualified_only\r\n")
    write(tmp_path / rel, entries_in_other_order)
    verdict = LibraryManager(None).export(lm, LM, rel,
                                          export_context(tmp_path, rel))
    assert verdict == "updated"
    with io.open(str(tmp_path / rel), encoding="utf-8") as f:
        assert f.read().startswith(u"# cdsint library list")


def test_export_still_protects_a_real_edit_nobody_imported(tmp_path):
    lm = a_project_libman()
    rel = "Library Manager.libraries"
    write(tmp_path / rel, u"library CAA Memory, * (CAA Technical Workgroup)\n")
    verdict = LibraryManager(None).export(lm, LM, rel,
                                          export_context(tmp_path, rel))
    assert verdict == "pending"
