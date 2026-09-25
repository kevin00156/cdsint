# -*- coding: utf-8 -*-
"""What the whole-branch review of SPEC 6.10 found, each pinned by a test."""
import io
import os

from cds.core import device_text as dt
from engine import device_pass, device_params, object_create, sync_dir
from engine.codesys_constants import TYPE_GUIDS
from engine.sync_cache import load_sync_cache, save_sync_cache
from tests.device_fakes import a_slave
from tests.test_device_pass import PLC, a_project, empty_results, write


def test_a_compare_does_not_drop_the_devices_from_the_cache(tmp_path):
    # Without the entry the dirty-file guard forgets the file, and the next
    # export overwrote a device edit nobody had imported (SPEC 6.1).
    base = str(tmp_path)
    rel = PLC + "/EtherCAT_2.device"
    entry = {"ide_hash": "a", "disk_mtime": 5, "disk_size": 6}
    save_sync_cache(base, {rel: entry, "A/P.st": entry}, {}, {})
    before = load_sync_cache(base)["objects"]
    save_sync_cache(base, {"A/P.st": entry}, {}, {})   # what compare saves
    device_pass.keep_device_cache(base, before)
    assert load_sync_cache(base)["objects"][rel] == entry


def test_a_file_with_no_device_is_refused_even_when_its_name_matches_another(tmp_path):
    project, master, slave = a_project()
    write(str(tmp_path / PLC / "EtherCAT_2" / "Ghost.device"), u"device  1|2|3\n")
    results = device_pass.with_device_changes(empty_results(), str(tmp_path),
                                              project, {"devices": True})
    [ghost] = results["new_on_disk"]
    assert "does not create" in ghost["refused"] and ghost["device_pass"]


def test_a_file_whose_name_differs_only_in_case_is_the_devices_file(tmp_path):
    project, master, slave = a_project()
    for device, rel in device_pass.ethercat_devices(project):
        write(str(tmp_path / rel.lower()), device_params.render(device))
    results = device_pass.with_device_changes(empty_results(), str(tmp_path),
                                              project, {"devices": True})
    assert results["new_on_disk"] == [] and results["unchanged_count"] == 2


def test_device_files_are_sync_files_so_the_orphan_sweep_sees_them(tmp_path):
    write(str(tmp_path / "A" / "Old.device"), u"device  1|2|3\n")
    assert [r for r, _ in sync_dir.sync_files(str(tmp_path))] == ["A/Old.device"]


def test_the_object_sync_does_not_report_device_files_twice(tmp_path):
    project, master, slave = a_project()
    for device, rel in device_pass.ethercat_devices(project):
        write(str(tmp_path / rel), device_params.render(device))
    results = empty_results()
    rel = PLC + "/EtherCAT_2/X5_7SEtherCAT_1.device"
    results["new_on_disk"].append({"name": "X5", "path": rel,
                                   "file_path": str(tmp_path / rel)})
    results = device_pass.with_device_changes(results, str(tmp_path), project,
                                              {"devices": True})
    assert results["new_on_disk"] == []


def test_a_device_without_a_file_is_not_an_orphan_to_import(tmp_path):
    project, master, slave = a_project()
    results = device_pass.with_device_changes(empty_results(), str(tmp_path),
                                              project, {"devices": True})
    assert results["new_in_ide"] == []


def test_a_device_file_goes_to_the_device_manager_whatever_the_type(tmp_path):
    called = []

    class Recorder(object):
        def update(self, obj, file_path):
            called.append(file_path)
            return True
    managers = {TYPE_GUIDS["device"]: Recorder(), "default": None, "native": None}

    class Odd(object):
        type = "a-vendor-axis-guid"
    rel = PLC + "/EtherCAT_2/X5/Axis_1.device"
    assert object_create.update_existing_object(Odd(), rel, "f", managers)
    assert called == ["f"]


def test_a_value_line_left_out_is_not_a_difference():
    slave = a_slave()
    full = device_params.render(slave)
    fewer = "\n".join(l for l in full.splitlines()
                      if not l.startswith("c1/1074855936")) + "\n"
    assert dt.same(full, fewer)
    assert not dt.same(full, full.replace("c1/1074855936 = 0", "c1/1074855936 = 5"))


def test_a_pending_device_keeps_its_cache_entry_for_the_export_after(tmp_path):
    # Measured on 3.5.21.40: an edit left pending by one export was
    # overwritten by the next, because its entry did not reach the new cache.
    from engine import classify
    project, master, slave = a_project()
    rel = PLC + "/EtherCAT_2/X5_7SEtherCAT_1.device"
    write(str(tmp_path / rel), device_params.render(slave).replace(
        "c1/1627394048/Value = 6", "c1/1627394048/Value = 9"))
    entry = {"ide_hash": "x", "disk_mtime": 1, "disk_size": 1}
    context = {"export_dir": str(tmp_path), "exported_paths": set(),
               "new_cache": {}, "cache_data": {"objects": {rel: entry}}}
    managers = classify.create_import_managers(project)
    assert device_pass.export_devices(project, str(tmp_path), context,
                                      managers) == [rel]
    assert context["new_cache"][rel] == entry
