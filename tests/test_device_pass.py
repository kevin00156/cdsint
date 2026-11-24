# -*- coding: utf-8 -*-
"""The device pass beside the object sync (SPEC 6.10)."""
import io
import os

import pytest

from cds.core import device_text as dt
from engine import (classify, device_changes, device_pass, device_params,
                    import_items, unhandled)
from engine.codesys_constants import TYPE_GUIDS
from engine.managers_device import DeviceManager
from engine.sync_cache import normalize_path
from tests.device_fakes import (Connector, Device, Element, Ident, Mapping,
                                Port, a_master, a_slave)

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
    found = [(d.get_name(), rel) for d, rel in device_pass.synced_devices(project)]
    assert found == [
        ("EtherCAT_2", PLC + "/EtherCAT_2.device"),
        ("X5_7SEtherCAT_1", PLC + "/EtherCAT_2/X5_7SEtherCAT_1.device")]


def test_modules_under_a_coupler_port_are_found_under_the_port_folder():
    modules = [Device("Slave_%d" % n, Ident(65, "494350_%d" % n, "1"))
               for n in (2, 3)]
    coupler = Device("Slave_1", Ident(65, "494350_1", "1"),
                     children=[Port("Port 1", modules)])
    master = a_master(children=[coupler])
    project = Project([Device(PLC, Ident(4102, "0000 0005", "4.20.0.0"),
                              children=[master])])
    found = [rel for d, rel in device_pass.synced_devices(project)]
    assert found == [
        PLC + "/EtherCAT_2.device",
        PLC + "/EtherCAT_2/Slave_1.device",
        PLC + "/EtherCAT_2/Slave_1/Port 1/Slave_2.device",
        PLC + "/EtherCAT_2/Slave_1/Port 1/Slave_3.device"]


def test_a_non_device_above_the_master_is_not_walked():
    class Application(Port):
        def get_children(self, recursive=False):
            raise AssertionError("walked into an application")

    project, master, slave = a_project()
    project._children.append(Application("Application"))
    assert len(device_pass.synced_devices(project)) == 2


def a_builtin_tree(dio_connectors=None):
    """A Delta AX-8 as DIADesigner-AX 1.10 shows it (research 12): the
    controller, its BuiltIn folder and BuiltIn_DIO with one identification;
    the controller has device parameters, only BuiltIn_DIO has channels."""
    same = Ident(4102, "16f7 0412", "3.5.18.46")
    dio = Device("BuiltIn_DIO", same, connectors=dio_connectors or [
        Connector(1, [Element("35000", "", "In0", mapping=Mapping(None, "%IB224")),
                      Element("35601", "0", "X0 Filter Select")])])
    builtin = Device("BuiltIn", same, children=[dio])
    controller = Device("Device", same, params=[
        Element("55000", "TRUE", "Application Run Mode")],
        children=[a_master(), builtin])
    return Project([controller])


def test_outside_a_master_only_a_device_with_channels_is_found():
    found = [rel for d, rel in device_pass.synced_devices(a_builtin_tree())]
    assert found == ["Device/EtherCAT_2.device",
                     "Device/BuiltIn/BuiltIn_DIO.device"]


def test_a_device_whose_parameters_will_not_read_is_named_not_skipped():
    class Broken(object):
        connector_id = 1

        @property
        def host_parameters(self):
            raise RuntimeError("no parameters")

    unhandled.start()
    found = [rel for d, rel in
             device_pass.synced_devices(a_builtin_tree([Broken()]))]
    assert found == ["Device/EtherCAT_2.device"]
    # Its file, if there is one, must not be swept as an orphan.
    assert unhandled.names() == ["BuiltIn_DIO"]
    assert unhandled.any_file_unaccounted()


def test_unchanged_files_count_as_unchanged(tmp_path):
    project, master, slave = a_project()
    for device, rel in device_pass.synced_devices(project):
        write(str(tmp_path / rel), device_params.render(device))
    results = device_pass.with_device_changes(empty_results(), str(tmp_path),
                                              project, {"devices": True})
    assert results["unchanged_count"] == 2 and results["different"] == []


def test_an_edited_file_is_different_and_refused_while_devices_is_off(tmp_path):
    project, master, slave = a_project()
    for device, rel in device_pass.synced_devices(project):
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
                                      managers) == []
    rel = PLC + "/EtherCAT_2/X5_7SEtherCAT_1.device"
    with io.open(str(tmp_path / rel), encoding="utf-8") as f:
        assert dt.same(f.read(), device_params.render(slave))
    context["cache_data"] = {"objects": {normalize_path(rel): {"disk_mtime": 1,
                                                              "disk_size": 1}}}
    write(str(tmp_path / rel), device_params.render(slave).replace(
        "c1/1627394048/Value = 6", "c1/1627394048/Value = 8"))
    assert device_pass.export_devices(project, str(tmp_path), context,
                                      managers) == [rel]
