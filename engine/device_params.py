# -*- coding: utf-8 -*-
"""A device's parameters and channel mappings, read and written by the API.

SPEC 6.10. Every ReadWrite leaf outside a channel is a value; every mappable
channel (a channel or one of its bits) with a variable is a mapping; keys are the connector (or `dev`) and the path of
identifiers. Every write is read back, because the API reports success for
things that did not happen: a slave's DC cycle is replaced by the master's
(docs/ethercat-research.md 4.2), and the first write after opening a project
can raise and still leave the value (research 8.1). Reading everything first,
as apply() does, is what the research found avoids the second.
"""
from __future__ import print_function

from cds.core import device_text
from engine.strings import safe_str

READ_WRITE = "ReadWrite"
# A slave's DC sync0 and sync1 cycle times. They follow the master's
# MasterCycleTime times the slave's sync factor: a write to one is replaced,
# and a master cycle change reaches every slave by itself (research 4.2, the
# only values that changed on other devices). The factors are written; these
# are not.
FOLLOWS_MASTER = ("1610633216", "1610764288")
FOLLOWS_MASTER_WHY = ("follows the master's cycle; change the master's "
                      "MasterCycleTime or this slave's DC factor instead")


def _follows_master(key):
    parts = key.split("/")
    return len(parts) == 2 and parts[1] in FOLLOWS_MASTER


def _text(value):
    return u"" if value is None else safe_str(value)


def ident_of(device):
    found = device.get_device_identification()
    return u"%s|%s|%s" % (found.type, found.id, found.version)


def _is_channel(element):
    return bool(getattr(element, "is_mappable_io", False))


def _roots(device):
    """(key, parameter) for the device's own parameters and each connector's."""
    found = []
    for param in (getattr(device, "device_parameters", None) or []):
        found.append((u"dev/" + _text(param.identifier), param))
    for connector in device.connectors:
        head = u"c%s/" % connector.connector_id
        for param in connector.host_parameters:
            found.append((head + _text(param.identifier), param))
    return found


def _writable(param):
    return _text(param.offline_access_rights) == READ_WRITE


def _elements(device):
    """[(key, element, in_channel, writable)] for every parameter and
    sub-element, parents first. in_channel: the element is a channel or
    inside one. writable: its parameter's offline access is ReadWrite; a
    sub-element has no access rights of its own and takes its parameter's
    (measured on 3.5.21.40).

    A list built by plain loops, not a generator: IronPython 2.7 fails to
    compile a generator whose comprehension reuses an outer name ("Unable to
    cast FieldExpression to BlockExpression", measured on 3.5.21.40).
    """
    found = []
    stack = [(key, param, False, _writable(param))
             for key, param in reversed(_roots(device))]
    while stack:
        key, element, inside, writable = stack.pop()
        inside = inside or _is_channel(element)
        found.append((key, element, inside, writable))
        if element.has_sub_elements:
            subs = [(key + u"/" + _text(sub.identifier), sub, inside, writable)
                    for sub in element]
            stack.extend(reversed(subs))
    return found


def read(device):
    """(ident, values, maps, mappable): values and maps as (key, value,
    comment) triples for device_text.render, mappable the channel keys."""
    values, maps, mappable = [], [], set()
    for key, element, in_channel, writable in _elements(device):
        name = _text(element.visible_name)
        if _is_channel(element):
            mappable.add(key)
            variable = element.io_mapping.variable
            if variable:
                maps.append((key, _text(variable), u"%s, %s" % (
                    name, _text(element.io_mapping.manual_iec_address))))
        elif (writable and not in_channel and not element.has_sub_elements
              and not _follows_master(key)):
            values.append((key, _text(element.value), name))
    return ident_of(device), values, maps, mappable


def render(device):
    ident, values, maps, _ = read(device)
    return device_text.render(ident, values, maps)


def as_doc(device):
    return device_text.parse(render(device))[0]


def _write_value(index, key, value, problems):
    element, in_channel, writable = index.get(key, (None, False, False))
    if _follows_master(key):
        problems.append("%s: %s" % (key, FOLLOWS_MASTER_WHY))
    elif element is None:
        problems.append("%s: no such parameter on this device" % key)
    elif not writable or in_channel or element.has_sub_elements:
        problems.append("%s: read only" % key)
    else:
        element.value = value


def _write_mapping(index, key, variable, problems):
    element = index.get(key, (None, False, False))[0]
    if element is None or not _is_channel(element):
        problems.append("map %s: not a mappable channel" % key)
    else:
        element.io_mapping.variable = variable


def _guarded(write, index, key, value, problems, label):
    try:
        write(index, key, value, problems)
    except Exception as exc:
        problems.append("%s%s: %s" % (label, key, safe_str(exc)))


def apply(device, wanted):
    """Make the device's values and mappings what `wanted` says. Problems,
    by key; each write is tried whatever happened to the others."""
    index = dict((key, (element, inside, writable))
                 for key, element, inside, writable in _elements(device))
    changes = device_text.diff(as_doc(device), wanted)
    problems = []
    for key, value in sorted(changes["values"].items()):
        _guarded(_write_value, index, key, value, problems, "")
    for key, variable in sorted(changes["maps"].items()):
        _guarded(_write_mapping, index, key, variable, problems, "map ")
    reported = set(p.split(":")[0] for p in problems)
    problems.extend(p for p in device_text.mismatches(as_doc(device), wanted)
                    if p.split(":")[0] not in reported)
    return problems
