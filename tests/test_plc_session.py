# -*- coding: utf-8 -*-
"""plc login and plc logout in the watcher (design 5.1, 5.4).

The one property everything here pins: a plain login never changes the
controller. It logs in with Keep only when the IDE says nothing differs
(is_uptodate) and the controller holds this working copy's last download
(the identity check, docs/trace-research.md 17.4); otherwise it does nothing
and names the --method values that would. Every online call is preceded by
the credentials and the dialog switch (research 17.5) and runs inside one
nested script run (research 15.2).
"""
import json

import pytest

from engine import ide_private
from tests import plc_fakes
from tests.plc_fakes import (APP_HEADER_OLD, Application, Device, Online,
                             Session, download_info, ide, press)
from tests.plc_fakes import (   # noqa: F401  autouse fixtures
    fake_codesys_ui, keep_the_engine_loaded, workspace)

SECRET = "pa55-never-printed"
LOGIN = {"user": "dev", "password": SECRET}


@pytest.fixture(autouse=True)
def no_environment_login(monkeypatch):
    """The IDE's own environment holds no login, so what a test sees comes
    from the command's args or from nowhere."""
    monkeypatch.delenv("CDS_DEV_USER", raising=False)
    monkeypatch.delenv("CDS_DEV_PASS", raising=False)


@pytest.fixture(autouse=True)
def last_download_from_here(workspace):    # noqa: F811  the project's path
    """The IDE's download info beside the project, agreeing with the fake
    controller's Application.app header."""
    download_info()


def an_ide(allowed=("login",), **more):
    return ide(allowed=list(allowed), **more)


def session_of(ide_globals):
    return ide_globals["online"].session


def log_in(ide_globals, **args):
    return press(ide_globals, "login", args).result


def log_out(ide_globals, **args):
    return press(ide_globals, "logout", args).result


def logins(ide_globals):
    return [c for c in session_of(ide_globals).calls if c[0] == "login"]


# -- plc login, nothing to change --------------------------------------------

def test_an_unchanged_copy_logs_in_with_keep():
    ide_globals = an_ide()
    result = log_in(ide_globals)
    assert result["ok"], result["summary"]
    assert session_of(ide_globals).calls == [("login", "keep", False)]
    assert result["data"]["logged_in"] is True
    assert result["data"]["changed"] == "nothing"
    assert result["data"]["state"] == "run"


def test_already_logged_in_does_nothing_and_succeeds():
    ide_globals = an_ide()
    session_of(ide_globals).is_logged_in = True
    result = log_in(ide_globals)
    assert result["ok"], result["summary"]
    assert session_of(ide_globals).calls == []
    assert "already" in result["summary"]
    assert result["data"]["logged_in"] is True


def test_the_state_reported_is_the_one_read_after_the_login():
    ide_globals = an_ide()
    session_of(ide_globals).states_after_login = {"keep": "stop"}
    result = log_in(ide_globals)
    assert result["data"]["state"] == "stop"


def test_the_login_reports_the_address_it_reached():
    node = plc_fakes.DeviceNode("Device", plc_fakes.DEVICE_GUID)
    node.address = "3001.1000.2DDD.7F00.0001"
    node.gateway = "guid-1"
    gateway = plc_fakes.Gateway()
    gateway.guid = "guid-1"
    gateway.config_params = {0: "localhost", 1: 1217}
    ide_globals = an_ide(children=[node], gateways=[gateway])
    result = log_in(ide_globals)
    address = result["data"]["address"]
    assert "3001.1000.2DDD.7F00.0001" in address
    assert "Gateway-1" in address and "localhost:1217" in address
    assert address in result["summary"]


def test_a_node_that_will_not_say_its_address_reports_none():
    result = log_in(an_ide())
    assert result["ok"], result["summary"]
    assert result["data"]["address"] is None


# -- plc login, something would change -----------------------------------------

def test_an_unsaved_edit_refuses_the_plain_login():
    application = Application()
    application.is_uptodate = False
    application.is_online_change_possible = True
    ide_globals = an_ide(application=application)
    outcome = press(ide_globals, "login", {})
    result = outcome.result
    assert not result["ok"]
    assert logins(ide_globals) == []
    assert result["data"]["methods"] == ["download", "online_change"]
    assert result["data"]["uptodate"] is False
    assert outcome.needs is None
    summary = result["summary"]
    assert "--method download" in summary
    assert "--method online_change" in summary
    assert "nothing was done" in summary


def test_a_change_online_change_cannot_carry_offers_only_download():
    application = Application()
    application.is_uptodate = False
    application.is_online_change_possible = False
    ide_globals = an_ide(application=application)
    result = log_in(ide_globals)
    assert not result["ok"]
    assert logins(ide_globals) == []
    assert result["data"]["methods"] == ["download"]
    assert "--method online_change" not in result["summary"]


def test_an_ide_without_is_uptodate_is_refused():
    application = Application()
    del application.is_uptodate
    ide_globals = an_ide(application=application)
    result = log_in(ide_globals)
    assert not result["ok"]
    assert "is_uptodate" in result["summary"]
    assert logins(ide_globals) == []


def test_another_client_logged_in_says_so():
    ide_globals = an_ide()
    session_of(ide_globals).refuse_login = (
        "Login failed: the user is already logged in from another client")
    result = log_in(ide_globals)
    assert not result["ok"]
    assert "another client is logged in" in result["summary"]


def test_a_method_is_not_read_as_a_plain_login():
    ide_globals = an_ide(allowed=("login", "download"))
    result = log_in(ide_globals, method="download", yes=True)
    assert not result["ok"]
    assert session_of(ide_globals).calls == []


# -- the identity check (research 17.4) ---------------------------------------

def test_a_controller_holding_another_program_refuses_the_plain_login():
    device = Device(app=APP_HEADER_OLD)
    ide_globals = an_ide(device=device)
    result = log_in(ide_globals)
    assert not result["ok"]
    assert logins(ide_globals) == []
    assert "different download" in result["summary"]
    assert "--method download" in result["summary"]
    assert result["data"]["methods"] == ["download"]
    assert device.connected is False


def test_a_controller_holding_no_program_refuses_the_plain_login():
    device = Device(crc=None, app=None)
    ide_globals = an_ide(device=device)
    result = log_in(ide_globals)
    assert not result["ok"]
    assert logins(ide_globals) == []
    assert "Application.app" in result["summary"]
    assert "--method download" in result["summary"]
    assert device.connected is False


def test_the_identity_connection_is_closed_after_an_agreeing_check():
    device = Device()
    ide_globals = an_ide(device=device)
    assert log_in(ide_globals)["ok"]
    assert device.uploaded == ["PlcLogic/Application/Application.app"]
    assert device.connected is False


# -- plc logout ----------------------------------------------------------------

def test_logout_logs_out_and_reports_it():
    ide_globals = an_ide()
    session_of(ide_globals).is_logged_in = True
    result = log_out(ide_globals)
    assert result["ok"], result["summary"]
    assert session_of(ide_globals).calls == [("logout",)]
    assert result["data"]["logged_in"] is False
    assert "logged out" in result["summary"]


def test_logout_when_logged_out_succeeds_saying_so():
    ide_globals = an_ide()
    result = log_out(ide_globals)
    assert result["ok"], result["summary"]
    assert session_of(ide_globals).calls == []
    assert "not logged in" in result["summary"]


def test_a_logout_that_does_not_take_fails():
    ide_globals = an_ide()
    session = session_of(ide_globals)
    session.is_logged_in = True
    session.logout = lambda: session.calls.append(("logout",))
    result = log_out(ide_globals)
    assert not result["ok"]
    assert "logged_in" in result["summary"]


# -- one script run, credentials before every online call ----------------------

def counted_script_runs(monkeypatch):
    runs = []
    real = ide_private.in_script_run

    def counting(online_api, call):
        runs.append(online_api)
        return real(online_api, call)
    monkeypatch.setattr(ide_private, "in_script_run", counting)
    return runs


def test_every_online_call_runs_inside_one_script_run(monkeypatch):
    runs = counted_script_runs(monkeypatch)
    ide_globals = an_ide()
    assert log_in(ide_globals)["ok"]
    assert len(runs) == 1
    assert log_out(ide_globals)["ok"]
    assert len(runs) == 2


class LoggedSession(Session):
    def __init__(self, log, device):
        Session.__init__(self, device=device)
        self.log = log

    def login(self, option, delete_foreign_apps):
        self.log.append("login")
        Session.login(self, option, delete_foreign_apps)

    def logout(self):
        self.log.append("logout")
        Session.logout(self)


class LoggedOnline(Online):
    """The online API, writing every call that matters into one log."""

    def __init__(self, log):
        Online.__init__(self, gateways=[plc_fakes.Gateway()])
        self.log = log
        self.session = LoggedSession(log, self.device)

    @property
    def auth_fallback_modes(self):
        return self._fallback

    @auth_fallback_modes.setter
    def auth_fallback_modes(self, kinds):
        self.log.append("dialog off")
        self._fallback = kinds

    def set_default_credentials(self, user, password):
        self.log.append("credentials")
        Online.set_default_credentials(self, user, password)

    def create_online_device(self, node):
        self.log.append("create_online_device")
        return Online.create_online_device(self, node)

    def create_online_application(self, application):
        self.log.append("create_online_application")
        return Online.create_online_application(self, application)


ONLINE_CALLS = ("create_online_application", "create_online_device", "login",
                "logout")


def test_credentials_are_handed_over_before_every_online_call():
    log = []
    ide_globals = an_ide()
    ide_globals["online"] = LoggedOnline(log)
    login = press(ide_globals, "login", {"credentials": dict(LOGIN)})
    logout = press(ide_globals, "logout", {"credentials": dict(LOGIN)})
    assert login.ok() and logout.ok()
    called = [i for i, event in enumerate(log) if event in ONLINE_CALLS]
    assert [log[i] for i in called] == [
        "create_online_application", "create_online_device", "login",
        "create_online_application", "logout"]
    for i in called:
        assert log[i - 2:i] == ["dialog off", "credentials"], (i, log)
    assert ide_globals["online"].credentials == ("dev", SECRET)
    for outcome in (login, logout):
        written = (json.dumps(outcome.result) + outcome.stdout_tail
                   + repr(outcome.messages))
        assert SECRET not in written


def test_half_a_login_is_no_login():
    ide_globals = an_ide()
    result = log_in(ide_globals, credentials={"user": "dev", "password": ""})
    assert ide_globals["online"].credentials is None
    assert any("no credentials" in note for note in result["data"]["notes"])


def test_without_credentials_the_notes_say_none_were_given():
    ide_globals = an_ide()
    result = log_in(ide_globals)
    assert result["ok"], result["summary"]
    assert ide_globals["online"].credentials is None
    assert any("no credentials" in note for note in result["data"]["notes"])


# -- Force's bare refusal (research 17.2) --------------------------------------

class Watched(Application):
    """An application that writes when is_online_change_possible is read."""

    def __init__(self, log):
        Application.__init__(self)
        self.log = log

    @property
    def is_online_change_possible(self):
        self.log.append("is_online_change_possible")
        return True

    @is_online_change_possible.setter
    def is_online_change_possible(self, value):
        pass


def test_force_refusal_text_is_never_the_only_guard():
    log = []
    ide_globals = an_ide(application=Watched(log))
    online = LoggedOnline(log)
    ide_globals["online"] = online
    assert log_in(ide_globals)["ok"]
    assert "is_online_change_possible" in log
    assert log.index("is_online_change_possible") < log.index("login")
    forced = [c for c in online.session.calls
              if c[0] == "login" and c[1] == plc_fakes.OnlineChangeOption.Force]
    assert forced == []
