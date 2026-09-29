# -*- coding: utf-8 -*-
"""The EtherCAT device pass beside the object sync (SPEC 6.10)."""
import io
import os

import pytest

from cds.core import device_text as dt
from engine import (classify, device_changes, device_pass, device_params,
                    import_items, unhandled)
from engine.codesys_constants import TYPE_GUIDS
from engine.managers_device import DeviceManager
from engine.sync_cache import normalize_path
from tests.device_fakes import Device, Ident, a_master, a_slave

PLC = "CODESYS_Control_for_Linux_SL"


class Project(object):
    def __init__(self, children, app=None):
        self._children = children
        self.active_application = app
        self.path = "C:/p/Line.project"

    def get_children(self, recursive=False):
        return list(self._children)


def a_project():
    slave = a_slave()
    master = a_master(children=[slave])
    other = Device("BuiltIn", Ident(4102, "16f7 0412", "3.5.18.46"))
    plc = Device(PLC, Ident(4102, "0000 0005", "4.20.0.0"),
                 children=[master, other])
    return Project([plc]), master, slave


def write(path, text):
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(text)


def empty_results():
    return {"different": [], "new_in_ide": [], "new_on_disk": [], "moved": [],
            "unchanged_count": 0}


def test_only_the_ethercat_subtree_is_found_laid_out_like_the_tree():
    project, master, slave = a_project()
    found = [(d.get_name(), rel) for d, rel in device_pass.ethercat_devices(project)]
    assert found == [
        ("EtherCAT_2", PLC + "/EtherCAT_2.device"),
        ("X5_7SEtherCAT_1", PLC + "/EtherCAT_2/X5_7SEtherCAT_1.device")]


def test_unchanged_files_count_as_unchanged(tmp_path):
    project, master, slave = a_project()
    for device, rel in device_pass.ethercat_devices(project):
        write(str(tmp_path / rel), device_params.render(device))
    results = device_pass.with_device_changes(empty_results(), str(tmp_path),
                                              project, {"devices": True})
    assert results["unchanged_count"] == 2 and results["different"] == []


def test_an_edited_file_is_different_and_refused_while_devices_is_off(tmp_path):
    project, master, slave = a_project()
    for device, rel in device_pass.ethercat_devices(project):
        write(str(tmp_path / rel), device_params.render(device))
    rel = PLC + "/EtherCAT_2/X5_7SEtherCAT_1.device"
    write(str(tmp_path / rel), device_params.render(slave).replace(
        "c1/1627394048/Value = 6", "c1/1627394048/Value = 8"))
    results = device_pass.with_device_changes(empty_results(), str(tmp_path),
                                              project, {"devices": False})
    [item] = results["different"]
    assert item["path"] == rel and item["obj"] is slave
    assert "devices" in item["refused"]


def test_a_device_without_a_file_and_a_file_without_a_device(tmp_path):
    project, master, slave = a_project()
    write(str(tmp_path / PLC / "EtherCAT_2" / "Ghost.device"), u"device 1|2|3\n")
    results = device_pass.with_device_changes(empty_results(), str(tmp_path),
                                              project, {"devices": True})
    # A device with no file is not an orphan: import never deletes it.
    assert results["new_in_ide"] == []
    assert [i["path"] for i in results["new_on_disk"]] == [
        PLC + "/EtherCAT_2/Ghost.device"]


def test_the_manager_applies_and_the_report_says_so(tmp_path):
    class App(object):
        is_online_change_possible = False
    project, master, slave = a_project()
    project.active_application = App()
    device_changes.start()
    path = str(tmp_path / "X5.device")
    write(path, device_params.render(slave).replace(
        "c1/1627394048/Value = 6", "c1/1627394048/Value = 8"))
    assert DeviceManager(project).update(slave, path)
    assert device_changes.report(project) == {
        "devices_changed": ["X5_7SEtherCAT_1"], "full_download": True}


def test_the_manager_refuses_another_device_type(tmp_path):
    project, master, slave = a_project()
    path = str(tmp_path / "X5.device")
    write(path, device_params.render(slave).replace(
        "Revision=16#00000001", "Revision=16#00000002"))
    with pytest.raises(RuntimeError) as err:
        DeviceManager(project).update(slave, path)
    assert "identification" in str(err.value)


def test_the_manager_names_what_did_not_land(tmp_path):
    project, master, slave = a_project()
    path = str(tmp_path / "X5.device")
    write(path, device_params.render(slave).replace(
        "c1/1074855936 = 0", "c1/1074855936 = 65535"))
    with pytest.raises(RuntimeError) as err:
        DeviceManager(project).update(slave, path)
    assert "c1/1074855936: written 65535, the IDE has 0" in str(err.value)


def test_devices_have_the_device_manager():
    managers = classify.create_import_managers(project=None)
    for kind in ("device", "device_module"):
        assert isinstance(classify.manager_for(managers, TYPE_GUIDS[kind], True),
                          DeviceManager)


def test_import_refuses_a_refused_item_by_path(tmp_path):
    rel = PLC + "/EtherCAT_2.device"
    write(str(tmp_path / rel), u"")
    item = {"path": rel, "name": "EtherCAT_2", "type_guid": TYPE_GUIDS["device"],
            "device_pass": True, "refused": "devices is off"}
    tally = import_items._Tally()
    unhandled.start()
    batches, st_files = import_items._sort_items([item], str(tmp_path), None,
                                                 set(), tally)
    assert (batches, st_files, tally.failed) == ({}, [], 1)
    assert unhandled.records() == [{"name": rel, "reason": "devices is off"}]


def test_import_lets_an_allowed_device_item_through(tmp_path):
    rel = PLC + "/EtherCAT_2.device"
    write(str(tmp_path / rel), u"")
    item = {"path": rel, "name": "EtherCAT_2", "type_guid": TYPE_GUIDS["device"],
            "device_pass": True}
    batches, st_files = import_items._sort_items(
        [item], str(tmp_path), None, set(), import_items._Tally())
    assert st_files == [item]


def test_a_device_without_a_file_is_never_deleted(tmp_path):
    class Removable(object):
        removed = False

        def remove(self):
            self.removed = True
    obj = Removable()
    item = {"is_orphan": True, "obj": obj, "name": "EtherCAT_2",
            "type_guid": TYPE_GUIDS["device"], "device_pass": True,
            "path": PLC + "/EtherCAT_2.device"}
    tally = import_items._Tally()
    import_items._sort_items([item], str(tmp_path), None, set(), tally)
    assert not obj.removed and tally.deleted == 0


def test_a_device_file_is_never_created_as_something_else(tmp_path):
    rel = PLC + "/EtherCAT_2/Ghost.device"
    write(str(tmp_path / rel), u"device 1|2|3\n")
    with pytest.raises(RuntimeError) as err:
        import_items._create_st({"path": rel}, rel, str(tmp_path / rel), {}, {},
                                {}, None, import_items._Tally())
    assert "does not create" in str(err.value)


def test_export_writes_one_file_per_device_and_keeps_an_unimported_edit(tmp_path):
    project, master, slave = a_project()
    context = {"export_dir": str(tmp_path), "exported_paths": set(),
               "new_cache": {}, "cache_data": {"objects": {}}}
    managers = classify.create_import_managers(project)
    assert device_pass.export_devices(project, str(tmp_path), context,
                                      managers)[1] == []
    rel = PLC + "/EtherCAT_2/X5_7SEtherCAT_1.device"
    with io.open(str(tmp_path / rel), encoding="utf-8") as f:
        assert dt.same(f.read(), device_params.render(slave))
    context["cache_data"] = {"objects": {normalize_path(rel): {"disk_mtime": 1,
                                                              "disk_size": 1}}}
    write(str(tmp_path / rel), device_params.render(slave).replace(
        "c1/1627394048/Value = 6", "c1/1627394048/Value = 8"))
    assert device_pass.export_devices(project, str(tmp_path), context,
                                      managers)[1] == [rel]


# -- export, end to end -----------------------------------------------------

def export_run(monkeypatch, tmp_path, project):
    """export_project on this project, as the watcher would run it."""
    from cds.core import settings
    from engine import entry_export
    from tests.fakes import DeafSystem, Projects
    projects = Projects(project)
    monkeypatch.setattr(entry_export, "projects", projects, raising=False)
    monkeypatch.setattr(entry_export, "system", DeafSystem(), raising=False)
    sync = str(tmp_path / "sync")
    return lambda: entry_export.export_project(
        sync, settings.resolve({"save_after_export": False}), projects), sync


SLAVE = PLC + "/EtherCAT_2/X5_7SEtherCAT_1.device"


def test_an_export_counts_the_device_files_it_writes(monkeypatch, tmp_path):
    project, master, slave = a_project()
    run, _sync = export_run(monkeypatch, tmp_path, project)
    first = run()
    assert first["ok"] is True, first["summary"]
    assert (first["data"]["devices_new"], first["data"]["devices_updated"],
            first["data"]["devices_identical"]) == (2, 0, 0)
    assert "Devices" in first["summary"]


def test_an_export_rewrites_a_device_the_ide_changed(monkeypatch, tmp_path):
    # A device changed in the IDE after the last export: the file is the
    # side that is behind, and nothing on disk is lost by rewriting it.
    project, master, slave = a_project()
    run, sync = export_run(monkeypatch, tmp_path, project)
    assert run()["ok"] is True
    op_mode = slave.connectors[0].host_parameters[4]
    [_index, value] = list(op_mode)
    value._value = "8"

    second = run()

    assert second["ok"] is True, second["summary"]
    assert (second["data"]["devices_new"], second["data"]["devices_updated"],
            second["data"]["devices_identical"]) == (0, 1, 1)
    assert second["data"]["pending_import"] == []
    with io.open(os.path.join(sync, SLAVE), encoding="utf-8") as f:
        assert "c1/1627394048/Value = 8" in f.read()


def test_an_export_leaves_an_unimported_device_edit_pending(monkeypatch,
                                                            tmp_path):
    # The same rule as a .st (SPEC 6.1): the disk moved since the last sync,
    # so the file is somebody's work, waits for import, and the run is not ok.
    project, master, slave = a_project()
    run, sync = export_run(monkeypatch, tmp_path, project)
    assert run()["ok"] is True
    path = os.path.join(sync, SLAVE)
    with io.open(path, encoding="utf-8") as f:
        edited = f.read().replace("c1/1627394048/Value = 6",
                                  "c1/1627394048/Value = 9")
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(edited + u"# edited by hand\n")

    second = run()

    assert second["ok"] is False
    assert second["data"]["pending_import"] == [SLAVE]
    assert second["data"]["devices_updated"] == 0
    with io.open(path, encoding="utf-8") as f:
        assert "c1/1627394048/Value = 9" in f.read()
