# -*- coding: utf-8 -*-
"""EtherCAT devices as the script API shows them (docs/ethercat-research.md 3).

A parameter is a data element: identifier, visible name, value, offline
access rights; a compound one yields its sub-elements when iterated; a
mappable one has an io_mapping. A device has connectors with host
parameters, and device parameters of its own.
"""
from engine.codesys_constants import TYPE_GUIDS


class Mapping(object):
    def __init__(self, variable=None, address="%IW0"):
        self.variable = variable
        self.manual_iec_address = address


class Element(object):
    def __init__(self, identifier, value="", name=None, access="ReadWrite",
                 subs=(), mapping=None, on_write=None,
                 channel="None", bits=0):
        self.identifier = identifier
        self.visible_name = name or identifier
        self._value = value
        self.offline_access_rights = access
        self._subs = list(subs)
        self.is_mappable_io = mapping is not None
        self.io_mapping = mapping
        self.channel_type, self.bit_size = channel, bits
        self._on_write = on_write     # what the plug-in does with a write

    @property
    def has_sub_elements(self):
        return bool(self._subs)

    def __iter__(self):
        return iter(self._subs)

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, new):
        self._value = self._on_write(new) if self._on_write else new


class Sub(Element):
    """A sub-element of a parameter. Like the real ScriptValueDataElement it
    has no access rights of its own; those are the parameter's (measured on
    3.5.21.40: reading offline_access_rights off one raises)."""

    def __init__(self, *args, **kwargs):
        Element.__init__(self, *args, **kwargs)
        del self.offline_access_rights


class Connector(object):
    def __init__(self, connector_id, params):
        self.connector_id = connector_id
        self.host_parameters = list(params)


class Ident(object):
    def __init__(self, type_, id_, version):
        self.type, self.id, self.version = type_, id_, version


class Device(object):
    is_device = True

    def __init__(self, name, ident, connectors=(), params=(), children=(),
                 kind="device"):
        self._name = name
        self._ident = ident
        self.connectors = list(connectors)
        self.device_parameters = list(params)
        self.type = TYPE_GUIDS[kind]
        self.guid = "guid-" + name
        self.parent = None
        self._children = list(children)
        for child in self._children:
            child.parent = self

    def get_name(self):
        return self._name

    def get_device_identification(self):
        return self._ident

    def get_children(self, recursive=False):
        return list(self._children)


def a_slave(master_cycle="1000"):
    """An X5 drive: a DC cycle that follows the master, a startup SDO
    compound, a read-only line, and two channels, one mapped."""
    return Device("X5_7SEtherCAT_1",
                  Ident(65, "766_0001000000000001", "Revision=16#00000001"),
                  connectors=[Connector(1, [
                      Element("1610633216", "1000", "DC sync0 cycletime",
                              on_write=lambda new: master_cycle),
                      Element("1074855936", "0", "Physical Address of the Slave",
                              on_write=lambda new: "0" if new == "65535" else new),
                      Element("1610743808", "'x 1'", "DC sync0 factor"),
                      Element("805306688", "{True}", "Mailbox capabilities",
                              access="Read"),
                      Element("1627394048", "{16#6060, 6}", "Op mode", subs=[
                          Sub("Index", "16#6060"), Sub("Value", "6")]),
                      Element("33554435", "{FALSE}", "Error Code",
                              mapping=Mapping("Application.GVL_Axis.aDriveErrorCodes[1]",
                                              "%IW5"),
                              subs=[Sub("33554435_0", "FALSE", "Bit0",
                                        mapping=Mapping(None, "%IX10.0"))]),
                      Element("33554436", "{FALSE}", "Torque Actual Value",
                              mapping=Mapping(None, "%IW6")),
                  ])])


def a_master(children=()):
    return Device("EtherCAT_2", Ident(64, "0000 1002", "4.10.0.0"),
                  connectors=[Connector(2, [
                      Element("805326848", "1000", "MasterCycleTime")])],
                  children=children)


class Port(object):
    """A modular coupler's connector node ("Port 1" on an ICP DAS EC4-EP21,
    DIADesigner-AX 1.10): in the device tree, holding the modules, but not a
    device itself."""
    is_device = False

    def __init__(self, name, children=()):
        self._name = name
        self.parent = None
        self._children = list(children)
        for child in self._children:
            child.parent = self

    def get_name(self):
        return self._name

    def get_children(self, recursive=False):
        return list(self._children)


# A slave's process data as a `.device` file holds it: one RxPDO of 16 bits on
# SM 2, one TxPDO of 48 bits on SM 3, and another TxPDO of 32 bits that is
# unassigned until other_sm says otherwise. The ids are the plug-in's.
RX_PDO, TX_PDO, OTHER_TX_PDO = 1879048192, 1879375872, 1879376128


def pdo_values(other_sm="-1", in_length="6"):
    values = {}
    for number, length in enumerate(("16#80", "16#80", "2", in_length)):
        for field, value in (("length", length), ("flagtypedir", "32"),
                             ("flagctrl", "1"), ("synctype", "0")):
            values["c1/%d/%s" % (1342177281 + number, field)] = value
    for pdo, index, sm, sizes in ((RX_PDO, "16#1600", "2", (16,)),
                                  (TX_PDO, "16#1A00", "3", (16, 32)),
                                  (OTHER_TX_PDO, "16#1A05", other_sm, (32,))):
        for field, value in (("Index", index), ("Sm", sm),
                             ("Mandatory", "False"),
                             ("NumberofEntries", str(len(sizes)))):
            values["c1/%d/%s" % (pdo, field)] = value
        for place, size in enumerate(sizes):
            values["c1/%d/Size" % (pdo + 2 + place)] = str(size)
            values["c1/%d/SubIndex" % (pdo + 2 + place)] = str(place)
    return values
