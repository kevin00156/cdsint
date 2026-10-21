# -*- coding: utf-8 -*-
"""What has to hold before a Keep login can be trusted to change nothing.

A Keep login is not "change nothing": it puts whatever the working copy has
that the controller lacks onto it, by online change or by full download,
without asking (research 12.1, 17.3, 17.4; docs/ethercat-research.md 5.2).
Two questions together close that, and both plc trace and the watcher's
plain plc login ask them: does the IDE find the program unchanged since its
last download (is_uptodate), and does the controller hold that download
(its Application.app header against the copy's .bootinfo_guids)? Neither is
enough alone: a controller someone else downloaded to, or one holding no
application, leaves is_uptodate true (research 17.4).
"""
from __future__ import print_function

from engine import plc_crc, plc_identity
from engine.ide_read import name_of


def uptodate(application):
    """(is_uptodate, None), or (None, why it cannot be told).

    An IDE without it cannot promise the login changes nothing, and is
    refused rather than trusted.
    """
    answer = getattr(application, "is_uptodate", None)
    if answer is None:
        return None, ("this IDE's application object has no is_uptodate, so "
                      "there is no way to tell whether a Keep login would "
                      "download; nothing was logged in to")
    if not isinstance(answer, bool):
        # A method, or a proxy that is truthy whatever it holds, would read
        # as "unchanged" to a bare `if not`; the gate only opens on an
        # answer that can only mean yes.
        return None, ("this IDE's is_uptodate is %r, not true or false, so "
                      "there is no way to tell whether a Keep login would "
                      "download; nothing was logged in to" % (answer,))
    return answer, None


def the_ide_agrees(trip, cure=plc_identity.DOWNLOAD):
    """The controller holds the download this copy's IDE files describe.

    None when it does, or the problem. Through trip.connected, so the
    device connection is cdsint's own and always closed again, and nothing
    logs in to the application (research 17.4). `cure` replaces what every
    plc_identity refusal ends with: the watcher has no plc download, and
    sends the caller elsewhere.
    """
    problem = trip.connected(lambda: _judged(trip))
    if problem:
        return problem.replace(plc_identity.DOWNLOAD, cure)
    return None


def _judged(trip):
    local, problem = trip.pull(trip.remote["app"])
    if problem:
        # A controller holding no application lands here too: its .app is
        # not there to fetch.
        return "%s; %s" % (problem, plc_identity.DOWNLOAD)
    code, problem = plc_identity.judged(
        plc_crc.read_bytes(local), trip.project_path(),
        name_of(trip.device_node), name_of(trip.application))
    if problem:
        return problem
    trip.note("download info agrees with the controller: code %s" % code)
    return None
