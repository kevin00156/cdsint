# -*- coding: utf-8 -*-
"""Tests for engine/plc_download_watch.py: plc download through the IDE
somebody has open, leaving it as it was found."""
from cds.core import trace_run
from cds.ide import silent
from engine import plc_crc
import tests.plc_fakes as plc_fakes
from tests.plc_fakes import CRC_B, Device, Gateway, PLC_BODY, at, ide
from tests.plc_fakes import (   # noqa: F401  autouse fixtures
    fake_codesys_ui, keep_the_engine_loaded, workspace)

LOGIN = {"user": "u", "password": "p"}


def watcher_ide(aimed=True, logged_in=False, gateways=None):
    """The --project fake, made the watcher's: no wait lent (SPEC D5)."""
    gateways = gateways or [Gateway()]
    ide_globals = ide(allowed=["download"], device=Device(crc=CRC_B),
                      gateways=gateways)
    del ide_globals[trace_run.HOLD_GLOBAL]
    node = ide_globals["projects"].primary.get_children()[0]
    if aimed:
        node.gateway, node.address = gateways[0].guid, "0000.0001"
    else:
        node.gateway, node.address = gateways[0].guid, "0000.0099"
    ide_globals["online"].session.is_logged_in = logged_in
    return ide_globals


def download(ide_globals, **more):
    args = at(yes=True, after="s.3", credentials=LOGIN, gateway_name=None)
    args.update(more)
    return silent.run(ide_globals, PLC_BODY, "download", args)


def calls(ide_globals):
    return [c[0] for c in ide_globals["online"].session.calls]


def test_it_downloads_starts_logs_out_and_records_like_the_project_form():
    ide_globals = watcher_ide()
    outcome = download(ide_globals)
    assert outcome.ok(), outcome.result["summary"]
    assert calls(ide_globals) == ["login", "create_boot_application",
                                  "start", "logout"]
    data = outcome.result["data"]
    assert data["crc"] == plc_crc.MATCH and data["logged_in"] is False
    written = plc_crc.read_records(
        plc_crc.record_path(plc_fakes.PROJECT_PATH))
    assert list(written) == [plc_fakes.CONTROLLER]


def test_the_device_node_is_checked_not_aimed():
    ide_globals = watcher_ide()
    download(ide_globals)
    node = ide_globals["projects"].primary.get_children()[0]
    assert node.gateway_set_to is None


def test_a_node_pointing_elsewhere_is_refused_before_anything_is_sent():
    ide_globals = watcher_ide(aimed=False)
    outcome = download(ide_globals)
    assert not outcome.ok()
    assert "not re-aimed" in outcome.result["summary"]
    assert calls(ide_globals) == []


def test_a_node_behind_another_gateway_is_refused():
    gateways = [Gateway("Gateway-1"), Gateway("Gateway-3")]
    ide_globals = watcher_ide(gateways=gateways)
    outcome = download(ide_globals, gateway_name="Gateway-3")
    assert not outcome.ok() and calls(ide_globals) == []


def test_an_ide_that_is_logged_in_is_left_alone():
    # Somebody's session: a person's, a plc login's, a recording's.
    ide_globals = watcher_ide(logged_in=True)
    outcome = download(ide_globals)
    assert not outcome.ok()
    assert "plc logout first" in outcome.result["summary"]
    assert calls(ide_globals) == []


def test_without_a_count_nothing_is_done():
    # The CLI never sends one without it; the wire is not trusted.
    ide_globals = watcher_ide()
    outcome = download(ide_globals, after=None)
    assert not outcome.ok() and "--after" in outcome.result["summary"]
    assert calls(ide_globals) == []


def test_without_a_gateway_nothing_is_done():
    ide_globals = watcher_ide()
    outcome = download(ide_globals, gateway=None)
    assert not outcome.ok() and "--gateway" in outcome.result["summary"]


def test_the_login_is_handed_over_before_the_online_calls():
    ide_globals = watcher_ide()
    download(ide_globals)
    assert ide_globals["online"].credentials == ("u", "p")


def test_without_a_forwarded_login_nothing_is_sent():
    ide_globals = watcher_ide()
    outcome = download(ide_globals, credentials=None)
    assert not outcome.ok() and "device login" in outcome.result["summary"]
    assert calls(ide_globals) == []
