# -*- coding: utf-8 -*-
"""A file whose object export skips on purpose is not an orphan.

An import_only kind, or an XML kind with export_xml off, still has an object
in the project and a file somebody committed. Export does not write it, and
until now it did not claim it either, so the orphan sweep deleted it.
"""
import pytest

from engine import classify, entry_export, sync_cache
from engine.codesys_constants import TYPE_GUIDS

from cds.core import settings
from tests.fakes import DeafSystem, Project, Projects


class Visu(object):
    parent = None
    guid = "guid-visu"
    type = TYPE_GUIDS["pou"]

    def get_name(self):
        return "MainVisu"

    def get_children(self, recursive=False):
        return []


@pytest.mark.parametrize("reason", [classify.SKIP_XML_GATE,
                                    classify.SKIP_SYNC_DIRECTION])
def test_a_skipped_objects_file_is_not_swept(monkeypatch, tmp_path, reason):
    sync = tmp_path / "sync"
    kept = sync / "MainVisu.visu.xml"
    sync.mkdir()
    kept.write_text(u"<visu/>", encoding="utf-8")
    # Left by the last sync and untouched since: without the claim this is
    # an orphan the sweep deletes, so the test fails if the claim goes.
    mtime, size = sync_cache.file_signature(str(kept))
    sync_cache.save_sync_cache(str(sync), {"mainvisu.visu.xml": {
        "disk_mtime": mtime, "disk_size": size}})
    projects = Projects(Project({}, [Visu()], str(tmp_path / "Fake.project")))
    monkeypatch.setattr(entry_export, "system", DeafSystem(), raising=False)
    monkeypatch.setattr(
        entry_export, "resolve_object",
        lambda obj, guid, types, export_xml, project: classify.Resolved(
            obj.type, True, "MainVisu.visu.xml", reason, "miss"))
    values = settings.resolve({"auto_delete_orphans": True})

    entry_export.export_project(str(sync), values, projects)

    assert kept.read_text(encoding="utf-8") == u"<visu/>"
