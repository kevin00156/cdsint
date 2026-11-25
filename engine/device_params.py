# -*- coding: utf-8 -*-
"""A device's parameters and channel mappings, read and written by the API.

SPEC 6.10. Every ReadWrite leaf outside a channel is a value; every mappable
channel (a channel or one of its bits) is a mapping, with "" for no variable;
keys are the connector (or `dev`) and the path of identifiers. Every write is read back, because the API reports success for
things that did not happen: a slave's DC cycle is replaced by the master's
(docs/ethercat-research.md 4.2), and the first write after opening a project
can raise and still leave the value (research 8.1). Reading everything first,
as apply() does, is what the research found avoids the second. A slave's PDO
assignment is the one value not written this way: the plug-in has to rebuild
the channel list with it (engine/pdo_assignment.py).
"""
from __future__ import print_function

from cds.core import device_text, pdo_layout
from engine import pdo_assignment
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

OLD_NUMBERING = ("map %s: numbered for the channel list before this PDO "
                 "assignment, so no mapping was written; the IDE kept every "
                 "variable on its channel. Delete the file and export to get "
                 "the new numbers")


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


def has_channel(device):
    for entry in _elements(device):
        if _is_channel(entry[1]):
            return True
    return False


def read(device):
    """(ident, values, maps): (key, value, comment) triples for
    device_text.render. maps has every channel, "" for no variable."""
    values, maps = [], []
    for key, element, in_channel, writable in _elements(device):
        name = _text(element.visible_name)
        if _is_channel(element):
            maps.append((key, _text(element.io_mapping.variable), u"%s, %s" % (
                name, _text(element.io_mapping.manual_iec_address))))
        elif (writable and not in_channel and not element.has_sub_elements
              and not _follows_master(key)):
            values.append((key, _text(element.value), name))
    return ident_of(device), values, maps


def render(device):
    ident, values, maps = read(device)
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


def _index(device):
    return dict((key, (element, inside, writable))
                for key, element, inside, writable in _elements(device))


def _write_values(device, changes, problems):
    index = _index(device)
    for key, value in sorted(changes.items()):
        _guarded(_write_value, index, key, value, problems, "")


def _write_mappings(device, changes, problems):
    index = _index(device)
    for key, variable in sorted(changes.items()):
        _guarded(_write_mapping, index, key, variable, problems, "map ")


def _write(device, have, wanted, problems):
    changes = device_text.diff(have, wanted)
    _write_values(device, changes["values"], problems)
    _write_mappings(device, changes["maps"], problems)


def _write_with_pdos(device, have, wanted, change, problems):
    """_write(), for a file that also changes the PDO assignment.

    The assignment goes first, because the rebuild renumbers the channels
    the mappings are for, and once more after the values, because channels
    take their names from them. A value the rebuild set itself is the IDE's
    to compute: writing the file's older one back would put the layout out
    of step again, so it is left for the read-back to name. A file whose map
    lines are numbered for the old list maps nothing: the rebuild has kept
    every variable on its channel, and those lines would move them off it.
    """
    change.rebuild()
    rebuilt = as_doc(device)
    values = device_text.diff(rebuilt, wanted)["values"]
    _write_values(device, dict(
        (key, value) for key, value in values.items()
        if rebuilt["values"].get(key) == have["values"].get(key)), problems)
    change.rebuild()
    stale = pdo_layout.old_numbering(have, rebuilt, wanted)
    if stale:
        problems.extend(OLD_NUMBERING % key for key in stale)
        return
    _write_mappings(device, device_text.diff(as_doc(device), wanted)["maps"],
                    problems)


def apply(device, wanted):
    """Make the device's values and mappings what `wanted` says. Problems,
    by key; each write is tried whatever happened to the others, except that
    a file whose PDO layout cannot be applied changes nothing."""
    have = as_doc(device)
    change = pdo_assignment.Change(device, have, wanted)
    refused = change.refusals()
    if refused:
        return ["nothing changed: " + "; ".join(refused)]
    problems = []
    if change.moved:
        _write_with_pdos(device, have, wanted, change, problems)
    else:
        _write(device, have, wanted, problems)
    after = as_doc(device)
    reported = set(p.split(":")[0] for p in problems)
    problems.extend(p for p in device_text.mismatches(after, wanted)
                    if p.split(":")[0] not in reported)
    return problems + pdo_assignment.leftovers(device, after)
