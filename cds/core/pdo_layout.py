# -*- coding: utf-8 -*-
"""Does a slave's channel list match the PDOs assigned to its sync managers?

SPEC 6.10. The IDE keeps three accounts of a slave's process data and only
its own Process Data page keeps them together: which PDOs are assigned (each
PDO's `Sm`), the sync managers' lengths, and the channels the process image
is laid out from. Written value by value the first two move and the channels
do not, and every slave behind this one then reads the wrong bytes (GitHub
#16). Plain Python on the values of a `.device` file; the channels' sizes
come from the IDE (engine/pdo_assignment.py).
"""
from __future__ import print_function

INPUT, OUTPUT = "Input", "Output"
UNASSIGNED = "-1"
# The EtherCAT plug-in's own numbering of a slave's PDO parameters, the same
# for every slave: each PDO's entries follow it within one stride, and the
# TxPDOs (the slave's inputs) come after every RxPDO.
PDO_STRIDE = 0x100
FIRST_TX_PDO = 0x70050000


def _number(text):
    """A value as the API writes it: 40, 16#28, or nothing at all."""
    text = (text or "").strip()
    return int(text[3:], 16) if text.startswith("16#") else int(text or 0)


def _parameters(values):
    """{connector: {parameter id: {field: value}}} for every compound."""
    found = {}
    for key, value in values.items():
        parts = key.split("/")
        if len(parts) == 3 and parts[1].isdigit():
            fields = found.setdefault(parts[0], {})
            fields.setdefault(int(parts[1]), {})[parts[2]] = value
    return found


def _is_pdo(fields):
    return "Sm" in fields and "NumberofEntries" in fields


def _is_entry(fields):
    return "Size" in fields and "SubIndex" in fields


def _pdos(params):
    """[(id, fields, bits, entries found)] of one connector's PDOs."""
    found = []
    for pdo_id in sorted(i for i in params if _is_pdo(params[i])):
        sizes = [_number(params[i]["Size"]) for i in params
                 if pdo_id < i < pdo_id + PDO_STRIDE and _is_entry(params[i])]
        found.append((pdo_id, params[pdo_id], sum(sizes), len(sizes)))
    return found


def _syncs(params):
    """The sync managers' fields, in order: the n-th is SM n."""
    return [params[i] for i in sorted(params)
            if "flagtypedir" in params[i] and "length" in params[i]]


def moved(have, wanted):
    """{key: SM number} for each PDO the file puts on another sync manager."""
    found = {}
    for connector, params in _parameters(have["values"]).items():
        for pdo_id, fields, _bits, _count in _pdos(params):
            key = "%s/%d/Sm" % (connector, pdo_id)
            new = wanted["values"].get(key, fields["Sm"])
            if new != fields["Sm"]:
                found[key] = new
    return found


def merged(have, wanted):
    """The values the device would hold with the file's written over them."""
    values = dict(have["values"])
    values.update((key, value) for key, value in wanted["values"].items()
                  if key in values)
    return values


def resized(have, wanted):
    """The keys of entry sizes the file changes."""
    found = []
    for connector, params in _parameters(have["values"]).items():
        keys = ["%s/%d/Size" % (connector, i) for i in params
                if _is_entry(params[i])]
        found.extend(k for k in keys if wanted["values"].get(
            k, have["values"][k]) != have["values"][k])
    return sorted(found)


def length_problems(values):
    """Where a sync manager and the PDOs assigned to it disagree.

    A module of a modular drive has PDOs and no sync managers of its own
    (they are its coupler's), so it has nothing to disagree with.
    """
    found = []
    for connector, params in sorted(_parameters(values).items()):
        syncs = _syncs(params)
        if not syncs:
            continue
        bits = {}
        for _id, fields, size, _count in _pdos(params):
            if fields["Sm"] != UNASSIGNED:
                bits[fields["Sm"]] = bits.get(fields["Sm"], 0) + size
        for sm in sorted(bits):
            found.extend(_one_length(connector, syncs, sm, bits[sm]))
    return found


def _one_length(connector, syncs, sm, bits):
    if not sm.isdigit() or int(sm) >= len(syncs):
        return ["%s: there is no sync manager %s" % (connector, sm)]
    want, have = (bits + 7) // 8, _number(syncs[int(sm)]["length"])
    if want == have:
        return []
    return ["%s: the PDOs on sync manager %s are %d bytes and its length is %d"
            % (connector, sm, want, have)]


def channel_problems(values, channel_bits):
    """Where the channels and the assigned PDOs disagree. channel_bits is
    {connector: {INPUT: bits, OUTPUT: bits}}.

    A connector with PDOs and no channel at all is a modular drive whose
    module carries the channels; there is nothing on it to compare.
    """
    found = []
    for connector, params in sorted(_parameters(values).items()):
        pdos = _pdos(params)
        channels = channel_bits.get(connector, {})
        if pdos and any(channels.values()):
            found.extend(_entry_counts(connector, pdos))
            found.extend(_one_list(connector, pdos, channels))
    return found


def _entry_counts(connector, pdos):
    return ["%s: PDO %s says it has %s entries and has %d"
            % (connector, fields.get("Index", ""), fields["NumberofEntries"],
               count)
            for _id, fields, _bits, count in pdos
            if count != _number(fields["NumberofEntries"])]


def _one_list(connector, pdos, channels):
    bits = {INPUT: 0, OUTPUT: 0}
    for pdo_id, fields, size, _count in pdos:
        if fields["Sm"] != UNASSIGNED:
            bits[INPUT if pdo_id >= FIRST_TX_PDO else OUTPUT] += size
    return ["%s: the assigned PDOs are %d %s bits and the channels are %d"
            % (connector, bits[side], side.lower(), channels.get(side, 0))
            for side in (INPUT, OUTPUT)
            if bits[side] != channels.get(side, 0)]


def problems(values, channel_bits):
    return length_problems(values) + channel_problems(values, channel_bits)


def dropped_mandatory(have, wanted):
    """The mandatory PDOs the file takes off their sync manager."""
    values = have["values"]
    return sorted(key for key, sm in moved(have, wanted).items()
                  if sm == UNASSIGNED
                  and values.get(key[:-len("Sm")] + "Mandatory") == "True")


def old_numbering(have, rebuilt, wanted):
    """The mapped keys of a file still numbered as before the rebuild.

    The rebuild keeps each variable on its PDO entry, whose channel may have
    a new key. A map line the file did not change, whose variable is no
    longer at that key, was written for the old numbering, and its key may
    by now be another channel's.
    """
    return sorted(key for key, variable in wanted["maps"].items()
                  if variable and have["maps"].get(key) == variable
                  and rebuilt["maps"].get(key) != variable)


def can_rebuild(values, channel_bits, connector):
    """Is this connector one whose channel list the IDE rebuilds: sync
    managers and channels of its own? A modular drive and its modules are
    not, and no rebuild of one was ever measured."""
    params = _parameters(values).get(connector, {})
    return bool(_syncs(params)) and any(
        channel_bits.get(connector, {}).values())
