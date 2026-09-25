# -*- coding: utf-8 -*-
"""A device's parameters and mappings, read and written (SPEC 6.10)."""
from cds.core import device_text as dt
from engine import device_params as dp
from tests.device_fakes import a_slave

IDENT = "65|766_0001000000000001|Revision=16#00000001"


def doc_of(device):
    ident, values, maps, _ = dp.read(device)
    return dt.parse(dt.render(ident, values, maps))[0]


def test_read_takes_readwrite_leaves_and_mapped_channels():
    # A channel and its bits are mappings, never values: their value is the
    # process image, and the sample project has 12296 of them.
    ident, values, maps, mappable = dp.read(a_slave())
    assert ident == IDENT
    # The DC cycle times follow the master's cycle times the factor
    # (research 4.2), so they are not the file's; the factor is.
    assert sorted(k for k, _, _ in values) == [
        "c1/1074855936", "c1/1610743808", "c1/1627394048/Index",
        "c1/1627394048/Value"]
    assert maps == [("c1/33554435", "Application.GVL_Axis.aDriveErrorCodes[1]",
                     "Error Code, %IW5")]
    assert mappable == set(["c1/33554435", "c1/33554435/33554435_0",
                            "c1/33554436"])


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
