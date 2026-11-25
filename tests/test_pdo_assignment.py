# -*- coding: utf-8 -*-
"""Importing a file that changes a slave's PDO assignment (SPEC 6.10, #16)."""
import pytest

from cds.core import device_text as dt
from engine import device_changes, device_params as dp, ide_private
from engine.managers_device import DeviceManager
from tests.device_fakes import (
    OTHER_TX_PDO, TX_PDO, Connector, Device, Element, Ident, Mapping, Sub,
    pdo_values)

SM_KEY = "c1/%d/Sm" % OTHER_TX_PDO


def compounds(values):
    """The parameters behind pdo_values' keys, as the API shows them."""
    grouped = {}
    for key, value in sorted(values.items()):
        _connector, param_id, field = key.split("/")
        grouped.setdefault(param_id, []).append(Sub(field, value))
    return [Element(param_id, "", subs=subs)
            for param_id, subs in sorted(grouped.items())]


def channel(key, side, bits, variable=None):
    return Element(key, "0", "channel " + key, access="None", channel=side,
                   bits=bits, mapping=Mapping(variable))


def a_slave(channels=None, **values):
    if channels is None:
        channels = [channel("16777218", "Output", 16),
                    channel("33554434", "Input", 32),
                    channel("33554435", "Input", 16, "xLast")]
    return Device("Slave_2", Ident(65, "a", "1"),
                  connectors=[Connector(1, compounds(pdo_values(**values))
                                        + channels)])


class Plugin(object):
    """The plug-in's save: the PDO on its SM, the lengths, a new channel
    list. The extra PDO's channel comes first, so "xLast" gets a new key."""

    def __init__(self, device, broken=False):
        self.connector = device.connectors[0]
        self.calls = []
        self.broken = broken

    def saver_for(self, connector):
        return self.save

    def save(self, sms):
        self.calls.append(sms)
        on = sms[OTHER_TX_PDO] != -1
        values = {}
        for param in self.connector.host_parameters:
            for sub in param:
                values["c1/%s/%s" % (param.identifier, sub.identifier)] = sub.value
        values[SM_KEY] = str(sms[OTHER_TX_PDO])
        values["c1/1342177284/length"] = "10" if on else "6"
        channels = [channel("16777218", "Output", 16),
                    channel("33554434", "Input", 32),
                    channel("33554435", "Input", 32)]
        if on and not self.broken:
            channels.append(channel("33554436", "Input", 16, "xLast"))
        self.connector.host_parameters = compounds(values) + channels


def wanted_of(device):
    return dt.parse(dp.render(device))[0]


@pytest.fixture
def slave():
    return a_slave()


@pytest.fixture
def plugin(slave, monkeypatch):
    made = Plugin(slave)
    monkeypatch.setattr(ide_private, "pdo_saver_for", made.saver_for)
    return made


def moved_file(slave):
    """What an export made after the same change in the IDE holds."""
    wanted = wanted_of(slave)
    wanted["values"][SM_KEY] = "3"
    wanted["values"]["c1/1342177284/length"] = "10"
    wanted["maps"] = {"c1/33554436": "xLast", "c1/33554435": "xNew"}
    return wanted


def test_a_moved_pdo_rebuilds_the_list_before_the_mappings(slave, plugin):
    assert dp.apply(slave, moved_file(slave)) == []
    after = wanted_of(slave)
    assert after["values"][SM_KEY] == "3"
    assert after["maps"] == {"c1/33554436": "xLast", "c1/33554435": "xNew"}
    # Again after the values: channels take their names from them.
    assert plugin.calls == [{OTHER_TX_PDO: 3}] * 2


def test_without_the_plug_ins_save_nothing_is_written(slave, monkeypatch):
    monkeypatch.setattr(ide_private, "pdo_saver_for", lambda connector: None)
    before = dp.render(slave)
    [problem] = dp.apply(slave, moved_file(slave))
    assert problem.startswith("nothing changed: c1: its PDO assignment changes")
    assert "Process Data page" in problem
    assert dp.render(slave) == before


def test_a_file_whose_length_is_not_its_assignments_is_refused(slave, plugin):
    wanted = moved_file(slave)
    wanted["values"]["c1/1342177284/length"] = "6"
    before = dp.render(slave)
    assert dp.apply(slave, wanted) == [
        "nothing changed: c1: the PDOs on sync manager 3 are 10 bytes and its "
        "length is 6"]
    assert dp.render(slave) == before and plugin.calls == []


@pytest.mark.parametrize("key, value, why", [
    ("c1/%d/Size" % (TX_PDO + 2), "64", "an entry's size changes"),
    (SM_KEY, "x", "there is no sync manager x"),
])
def test_what_no_rebuild_was_shown_to_do_is_refused(slave, plugin, key, value,
                                                    why):
    wanted = moved_file(slave)
    wanted["values"][key] = value
    [problem] = dp.apply(slave, wanted)
    assert problem.startswith("nothing changed: ") and why in problem
    assert plugin.calls == []


def test_a_mandatory_pdo_is_not_taken_off(plugin, slave):
    wanted = wanted_of(slave)
    for param in slave.connectors[0].host_parameters:
        for sub in param:
            if (param.identifier, sub.identifier) == (str(TX_PDO), "Mandatory"):
                sub.value = "True"
    wanted["values"]["c1/%d/Mandatory" % TX_PDO] = "True"
    wanted["values"]["c1/%d/Sm" % TX_PDO] = "-1"
    [problem] = dp.apply(slave, wanted)
    assert "the PDO is mandatory" in problem and plugin.calls == []


def test_a_drive_without_channels_of_its_own_is_refused(monkeypatch):
    drive = a_slave(channels=[])
    monkeypatch.setattr(ide_private, "pdo_saver_for", lambda c: 1 / 0)
    wanted = wanted_of(drive)
    wanted["values"][SM_KEY] = "3"
    [problem] = dp.apply(drive, wanted)
    assert "another device's" in problem


def test_a_size_alone_is_refused_before_it_is_written(slave, plugin):
    wanted = wanted_of(slave)
    wanted["values"]["c1/%d/Size" % (TX_PDO + 2)] = "64"
    before = dp.render(slave)
    [problem] = dp.apply(slave, wanted)
    assert problem.startswith("nothing changed: ")
    assert dp.render(slave) == before


def test_old_map_numbers_write_no_mapping(slave, plugin):
    wanted = moved_file(slave)
    wanted["maps"] = {"c1/33554435": "xLast"}
    problems = dp.apply(slave, wanted)
    assert problems[0].startswith("map c1/33554435: numbered for the channel "
                                  "list before")
    # The plug-in moved it with its PDO entry, and there it stays.
    assert wanted_of(slave)["maps"] == {"c1/33554436": "xLast"}


def test_a_value_the_rebuild_computed_is_named_not_written(slave, plugin):
    wanted = moved_file(slave)
    before = wanted_of(slave)["values"]
    wanted["values"]["c1/1342177284/flagctrl"] = "9"   # an ordinary value
    real = plugin.save

    def save(sms):
        real(sms)
        for param in slave.connectors[0].host_parameters:
            for sub in param:
                if (param.identifier, sub.identifier) == ("1342177284",
                                                          "synctype"):
                    sub.value = "computed"
    plugin.save = save
    problems = dp.apply(slave, wanted)
    assert problems == ["c1/1342177284/synctype: written %s, the IDE has "
                        "computed" % before["c1/1342177284/synctype"]]
    assert wanted_of(slave)["values"]["c1/1342177284/flagctrl"] == "9"


def test_the_guard_names_a_list_the_rebuild_left_wrong(slave, monkeypatch):
    plugin = Plugin(slave, broken=True)
    monkeypatch.setattr(ide_private, "pdo_saver_for", plugin.saver_for)
    wanted = moved_file(slave)
    wanted["maps"] = {}
    problems = dp.apply(slave, wanted)
    assert problems[-1].startswith("c1: the assigned PDOs are 80 input bits "
                                   "and the channels are 64")


def test_the_guard_fires_on_a_slave_that_was_stale_already(plugin):
    # What 0.7.0 left behind: 80 bits assigned, the list still 48.
    stale = a_slave(other_sm="3", in_length="10")
    wanted = wanted_of(stale)
    wanted["values"]["c1/1342177284/flagctrl"] = "9"
    [problem] = dp.apply(stale, wanted)
    assert "80 input bits and the channels are 48" in problem
    assert wanted_of(stale)["values"]["c1/1342177284/flagctrl"] == "9"


def test_a_stale_slaves_assignment_is_not_changed_here(plugin):
    stale = a_slave(other_sm="3", in_length="10")
    wanted = wanted_of(stale)
    wanted["values"][SM_KEY] = "-1"
    [problem] = dp.apply(stale, wanted)
    assert "before this import either" in problem and plugin.calls == []


def test_the_manager_reports_no_change_for_a_refusal(slave, monkeypatch,
                                                     tmp_path):
    monkeypatch.setattr(ide_private, "pdo_saver_for", lambda connector: None)
    path = tmp_path / "Slave_2.device"
    text = dp.render(slave).replace(SM_KEY + " = -1", SM_KEY + " = 3")
    path.write_text(text, encoding="utf-8")
    device_changes.start()
    with pytest.raises(RuntimeError, match="nothing changed"):
        DeviceManager().update(slave, str(path))
    assert device_changes.report(None)["devices_changed"] == []


def test_a_save_that_fails_raises_its_own_reason():
    class Net(Exception):
        class clsException(object):
            Message = "wrapper"

            class InnerException(object):
                Message, InnerException = "the reason", None

    def run(callback):
        try:
            callback("copy")
        except Exception:
            raise RuntimeError("target threw")

    def body(copy):
        raise Net("wrapper")
    with pytest.raises(RuntimeError, match="^the reason$"):
        ide_private._aborting(run, body)
    with pytest.raises(RuntimeError, match="^plain$"):
        ide_private._aborting(run, lambda copy: (_ for _ in ()).throw(
            ValueError("plain")))


def test_outside_an_ide_there_is_no_save():
    assert ide_private.pdo_saver_for(object()) is None
