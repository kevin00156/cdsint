# -*- coding: utf-8 -*-
"""Getting to the controller: which device, which gateway, whose credentials.

The link is the part that can go wrong before any comparison happens, and
the answers are all refusals rather than guesses (SPEC D7): more than one
device and it names them and stops, no gateway and it says so. The
credentials half is SPEC D14 — they come from the environment and reach no
command line, file or report.
"""
import pytest

from cds.ide import silent
from engine import plc_link
from tests.plc_fakes import (CredentialSourceKind, DEVICE_GUID, Device,
                             Gateway, DeviceNode, NoSwitch, Online, PLC_BODY, ide)
from tests.plc_fakes import (   # noqa: F401  autouse fixtures
    fake_codesys_ui, keep_the_engine_loaded, workspace)


# --------------------------------------------------------------------------

def test_a_project_with_no_device_says_so_rather_than_connecting():
    ide_globals = ide(allowed=["connect"], children=[DeviceNode("Application")])
    outcome = silent.run(ide_globals, PLC_BODY, "connect", {})
    assert not outcome.ok() and "no device node" in outcome.error_text()


def test_two_devices_are_named_and_nothing_is_picked():
    # Which controller to download to has no safe default and no flag to
    # answer it with, so the honest answer is to stop (SPEC D7).
    ide_globals = ide(allowed=["download"],
                      children=[DeviceNode("Left", DEVICE_GUID),
                                DeviceNode("Right", DEVICE_GUID)])
    outcome = silent.run(ide_globals, PLC_BODY, "download", {"yes": True})
    said = outcome.error_text()
    assert "Left" in said and "Right" in said
    assert ide_globals["online"].session.calls == []


def test_without_the_gateway_flag_the_projects_own_settings_are_left_alone():
    # A read-only command that rewrote the project's gateway on its way past
    # would be changing the project to answer a question about it.
    device_node = DeviceNode("Device", DEVICE_GUID)
    ide_globals = ide(allowed=["connect"], children=[device_node])
    silent.run(ide_globals, PLC_BODY, "connect", {})
    assert device_node.gateway_set_to is None


def test_the_gateway_flag_aims_the_device_and_says_where():
    gateway = Gateway()
    device_node = DeviceNode("Device", DEVICE_GUID)
    ide_globals = ide(allowed=["connect"], children=[device_node],
                      gateways=[gateway])
    outcome = silent.run(ide_globals, PLC_BODY, "connect",
                         {"gateway": "192.168.1.5", "port": 1217})
    assert device_node.gateway_set_to == (gateway, "192.168.1.5", 1217)
    assert gateway.asked == [("192.168.1.5", 1217)]
    assert any("192.168.1.5" in note
               for note in outcome.result["data"]["notes"])


def test_a_note_is_on_stdout_before_the_step_after_it_runs(capsys):
    # The four bench runs that hung were killed inside connect(), and their
    # stdout held nothing but the headless BEGIN mark: every note was sitting
    # in a list waiting for a result that never came, so nothing said which
    # step had stopped. Modelled with a connect() that ends the run instead
    # of failing it, because a failure still reaches result().
    class Killed(BaseException):
        """Not an Exception: the engine catches those and reports them."""

    class Unreachable(Device):
        def connect(self):
            raise Killed("the process went away")

    ide_globals = ide(allowed=["connect"], device=Unreachable(),
                      children=[DeviceNode("Device", DEVICE_GUID)],
                      gateways=[Gateway()])
    with pytest.raises(Killed):
        silent.run(ide_globals, PLC_BODY, "connect",
                   {"gateway": "192.168.1.5", "port": 11740})
    assert "192.168.1.5" in capsys.readouterr().out


def test_a_gateway_with_no_port_uses_the_standard_device_port():
    gateway = Gateway()
    device_node = DeviceNode("Device", DEVICE_GUID)
    ide_globals = ide(allowed=["connect"], children=[device_node],
                      gateways=[gateway])
    silent.run(ide_globals, PLC_BODY, "connect", {"gateway": "127.0.0.1"})
    assert gateway.asked == [("127.0.0.1", 11740)]


def test_asking_for_a_gateway_this_profile_does_not_have_stops_the_run():
    ide_globals = ide(allowed=["connect"], gateways=[])
    outcome = silent.run(ide_globals, PLC_BODY, "connect",
                         {"gateway": "192.168.1.5"})
    assert not outcome.ok() and "no gateway defined" in outcome.error_text()


# --------------------------------------------------------------------------
# Credentials (SPEC D14)
# --------------------------------------------------------------------------

def test_the_credential_dialog_is_switched_off_before_anything_connects():
    # Under --noUI a dialog nobody can answer is not a failure, it is a
    # process that never returns, so this is the line that makes the command
    # unattended at all.
    plc = plc_link
    online = Online()
    note, problem = plc.silence_credential_dialogs(
        online, {"CredentialSourceKind": CredentialSourceKind})
    assert problem is None
    assert online.auth_fallback_modes == "no-dialog"
    assert "auth_fallback_modes" in note


def test_an_ide_with_only_the_old_setter_is_switched_off_through_it():
    # 4.2.0.0 has the property and no method; 4.0.0.0 has not been looked at,
    # so the old spelling stays as a fallback instead of being deleted.
    plc = plc_link

    class OldApi(NoSwitch):
        def set_auth_fallback_modes(self, kinds):
            self._fallback = kinds

    online = OldApi()
    note, problem = plc.silence_credential_dialogs(
        online, {"CredentialSourceKind": CredentialSourceKind})
    assert problem is None
    assert online._fallback == "no-dialog"
    assert "set_auth_fallback_modes" in note


def test_a_credential_api_that_will_not_be_switched_off_stops_the_trip():
    # The old behaviour printed "will hang this run" and then went and hung.
    plc = plc_link
    note, problem = plc.silence_credential_dialogs(NoSwitch(), {
        "CredentialSourceKind": CredentialSourceKind})
    assert note is None
    assert "auth_fallback_modes" in problem and "never return" in problem


def test_an_ide_that_cannot_switch_the_dialog_off_never_connects():
    # The point of refusing is that connect() is the call that hangs, so it
    # must not be reached at all. Not a refusal in the permission sense
    # either: the project allowed this, the IDE cannot carry it out.
    device = Device()
    ide_globals = ide(allowed=["connect"], device=device)
    ide_globals["online"] = NoSwitch(device=device)
    outcome = silent.run(ide_globals, PLC_BODY, "connect", {})
    assert not outcome.ok()
    assert outcome.denied is None
    assert device.connected is False
    assert "never return" in outcome.result["summary"]


def test_the_login_comes_from_the_environment_and_nowhere_else(monkeypatch):
    plc = plc_link
    monkeypatch.setenv(plc.USER_ENV, "dev")
    monkeypatch.setenv(plc.PASS_ENV, "s3cret")
    online = Online()
    plc.silence_credential_dialogs(online, {"CredentialSourceKind":
                                            CredentialSourceKind})
    assert online.credentials == ("dev", "s3cret")


def test_no_environment_login_is_reported_rather_than_invented(monkeypatch):
    plc = plc_link
    monkeypatch.delenv(plc.USER_ENV, raising=False)
    online = Online()
    note, problem = plc.silence_credential_dialogs(
        online, {"CredentialSourceKind": CredentialSourceKind})
    assert problem is None and online.credentials is None
    assert plc.USER_ENV in note and plc.PASS_ENV in note


def test_the_password_reaches_no_part_of_what_gets_written_down(monkeypatch):
    # A report is committed or pasted into a ticket, so this is the test that
    # D14 is actually about. The user name is allowed through — knowing who
    # logged in is how a run is read afterwards.
    plc = plc_link
    monkeypatch.setenv(plc.USER_ENV, "dev")
    monkeypatch.setenv(plc.PASS_ENV, "s3cret-do-not-print")
    ide_globals = ide(allowed=["download"])
    outcome = silent.run(ide_globals, PLC_BODY, "download", {"yes": True})
    written = repr(outcome.result) + outcome.stdout_tail + repr(
        outcome.messages)
    assert "s3cret-do-not-print" not in written
    assert "dev" in written


# --------------------------------------------------------------------------
