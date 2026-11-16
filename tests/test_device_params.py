# -*- coding: utf-8 -*-
"""A device's parameters and mappings, read and written (SPEC 6.10)."""
from cds.core import device_text as dt
from engine import device_params as dp
from tests.device_fakes import a_slave

IDENT = "65|766_0001000000000001|Revision=16#00000001"


def doc_of(device):
    ident, values, maps = dp.read(device)
    return dt.parse(dt.render(ident, values, maps))[0]


def test_read_takes_readwrite_leaves_and_every_channel():
    # A channel and its bits are mappings, never values: their value is the
    # process image, and the sample project has 12296 of them.
    ident, values, maps = dp.read(a_slave())
    assert ident == IDENT
    # The DC cycle times follow the master's cycle times the factor
    # (research 4.2), so they are not the file's; the factor is.
    assert sorted(k for k, _, _ in values) == [
        "c1/1074855936", "c1/1610743808", "c1/1627394048/Index",
        "c1/1627394048/Value"]
    assert maps == [
        ("c1/33554435", "Application.GVL_Axis.aDriveErrorCodes[1]",
         "Error Code, %IW5"),
        ("c1/33554435/33554435_0", "", "Bit0, %IX10.0"),
        ("c1/33554436", "", "Torque Actual Value, %IW6")]


def test_a_channel_with_no_variable_is_a_commented_out_map_line():
    text = dp.render(a_slave())
    line = [l for l in text.splitlines() if "c1/33554436 " in l][0]
    assert line.startswith("# map c1/33554436 =")
    assert line.endswith("# Torque Actual Value, %IW6")
    assert dt.parse(text)[0]["maps"] == {
        "c1/33554435": "Application.GVL_Axis.aDriveErrorCodes[1]"}


def test_uncommenting_the_line_and_typing_a_variable_maps_the_channel():
    slave = a_slave()
    text = dp.render(slave).replace("# map c1/33554436 =",
                                    "map c1/33554436 = xTorque")
    wanted, problems = dt.parse(text)
    assert problems == []
    assert dp.apply(slave, wanted) == []
    assert doc_of(slave)["maps"]["c1/33554436"] == "xTorque"


def test_apply_writes_values_and_mappings():
    slave = a_slave()
    wanted = doc_of(slave)
    wanted["values"]["c1/1627394048/Value"] = "8"
    wanted["maps"]["c1/33554436"] = "xTorque"
    del wanted["maps"]["c1/33554435"]
    assert dp.apply(slave, wanted) == []
    after = doc_of(slave)
    assert after["values"]["c1/1627394048/Value"] == "8"
    assert after["maps"] == {"c1/33554436": "xTorque"}


def test_a_value_the_plug_in_replaces_is_named():
    slave = a_slave()
    wanted = doc_of(slave)
    wanted["values"]["c1/1074855936"] = "65535"
    assert dp.apply(slave, wanted) == [
        "c1/1074855936: written 65535, the IDE has 0"]


def test_a_dc_cycle_line_in_the_file_is_refused_not_written():
    slave = a_slave()
    wanted = doc_of(slave)
    wanted["values"]["c1/1610633216"] = "4000"
    assert dp.apply(slave, wanted) == [
        "c1/1610633216: follows the master's cycle; change the master's "
        "MasterCycleTime or this slave's DC factor instead"]


def test_an_unknown_or_read_only_key_is_named():
    slave = a_slave()
    wanted = doc_of(slave)
    wanted["values"]["c1/999"] = "1"
    wanted["values"]["c1/805306688"] = "{False}"
    wanted["maps"]["c1/1074855936"] = "xNotAChannel"
    problems = dp.apply(slave, wanted)
    assert "c1/999: no such parameter on this device" in problems
    assert "c1/805306688: read only" in problems
    assert "map c1/1074855936: not a mappable channel" in problems


def test_a_write_that_raises_is_named_and_the_rest_still_land():
    slave = a_slave()

    def refuse(new):
        raise Exception("Attempt to write an object with read-only access.")
    slave.connectors[0].host_parameters[1]._on_write = refuse
    wanted = doc_of(slave)
    wanted["values"]["c1/1074855936"] = "1001"
    wanted["values"]["c1/1627394048/Value"] = "8"
    problems = dp.apply(slave, wanted)
    assert problems == ["c1/1074855936: Attempt to write an object with "
                        "read-only access."]
    assert doc_of(slave)["values"]["c1/1627394048/Value"] == "8"
