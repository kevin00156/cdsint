# -*- coding: utf-8 -*-
"""Applying a change of a slave's PDO assignment, or refusing it (SPEC 6.10).

The rules are cds/core/pdo_layout.py's and the plug-in's save is
engine/ide_private.py's; this reads the channels' sizes off the device and
decides, before anything is written, whether the change can be made here.
"""
from __future__ import print_function

from cds.core import pdo_layout
from engine import ide_private
from engine.strings import safe_str

IN_THE_IDE = ("make this change on the slave's Process Data page in the IDE, "
              "then export")


def channel_bits(device):
    """{connector: {Input: bits, Output: bits}} over the device's channels.

    By channel type rather than by whether a channel can be mapped: one
    nobody can map takes its place in the process image all the same.
    """
    found = {}
    for connector in device.connectors:
        sums = {pdo_layout.INPUT: 0, pdo_layout.OUTPUT: 0}
        for param in connector.host_parameters:
            side = safe_str(param.channel_type)
            if side in sums:
                sums[side] += int(param.bit_size)
        found[u"c%s" % connector.connector_id] = sums
    return found


class Change(object):
    """One file's effect on one device's PDO assignment."""

    def __init__(self, device, have, wanted):
        self._device = device
        self._have = have
        self._wanted = wanted
        self._bits = channel_bits(device)
        self.moved = pdo_layout.moved(have, wanted)

    def refusals(self):
        """Why nothing of the file may be written; empty to go ahead."""
        before = pdo_layout.problems(self._have["values"], self._bits)
        after = pdo_layout.merged(self._have, self._wanted)
        if self.moved:
            return self._cannot_move(before, after)
        if before:
            # Not this file's doing. Its other lines are applied, and
            # leftovers() fails the device by name afterwards.
            return []
        return _in_the_ide(pdo_layout.problems(after, self._bits))

    def _cannot_move(self, before, after):
        if before:
            return _in_the_ide(["the channel list did not match the PDOs "
                                "before this import either (%s)"
                                % "; ".join(before)])
        fixed = pdo_layout.resized(self._have, self._wanted)
        if fixed:
            return _in_the_ide(["%s: an entry's size changes together with "
                                "the PDO assignment" % ", ".join(fixed)])
        needed = pdo_layout.dropped_mandatory(self._have, self._wanted)
        if needed:
            return ["%s: the PDO is mandatory" % ", ".join(needed)]
        return (_in_the_ide(self._cannot_rebuild())
                or pdo_layout.length_problems(after))

    def _cannot_rebuild(self):
        found = []
        for connector in sorted(set(key.split("/")[0] for key in self.moved)):
            if not pdo_layout.can_rebuild(self._have["values"], self._bits,
                                          connector):
                found.append("%s: its PDO assignment changes and its channels "
                             "or sync managers are another device's" % connector)
            elif self._saver(connector) is None:
                found.append("%s: its PDO assignment changes and this IDE's "
                             "EtherCAT plug-in offers no way to rebuild the "
                             "channel list" % connector)
        return found

    def _by_connector(self):
        """{connector: {PDO parameter id: SM number}} for the moved PDOs."""
        found = {}
        for key, sm in self.moved.items():
            connector, pdo_id, _field = key.split("/")
            found.setdefault(connector, {})[int(pdo_id)] = int(sm)
        return found

    def _saver(self, connector):
        for candidate in self._device.connectors:
            if u"c%s" % candidate.connector_id == connector:
                return ide_private.pdo_saver_for(candidate)
        return None

    def rebuild(self):
        """Assign the moved PDOs and rebuild the channel list from them."""
        for connector, sms in sorted(self._by_connector().items()):
            self._saver(connector)(sms)


def _in_the_ide(found):
    return ["%s; %s" % (text, IN_THE_IDE) for text in found]


def leftovers(device, doc):
    """What is wrong with the channel list after a file was applied. The
    guard: whatever was written, an IO image that does not match the PDOs
    is a failure by name (GitHub #16)."""
    return _in_the_ide(pdo_layout.problems(doc["values"],
                                           channel_bits(device)))
