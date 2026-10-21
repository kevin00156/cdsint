# -*- coding: utf-8 -*-
"""plc login, plc login --method and plc logout in the watcher (design 5.1
to 5.4).

The one property everything here pins: a plain login never changes the
controller. It logs in with Keep only when the IDE says nothing differs
(is_uptodate) and the controller holds this working copy's last download
(the identity check, docs/trace-research.md 17.4); otherwise it does nothing
and names the --method values that would. A --method changes it only after
-y, never by the other method's means (research 17.2), and never leaves the
CRC record answering MATCH for what it changed. Every online call is
preceded by the credentials and the dialog switch (research 17.5) and runs
inside one nested script run (research 15.2).
"""
import json

import pytest

from engine import ide_private, plc_crc, plc_session
from tests import plc_fakes
from tests.plc_fakes import (APP_HEADER_OLD, Application, Device, Online,
                             OnlineChangeOption, Session, download_info, ide,
                             press)
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


def test_a_method_that_is_no_method_is_refused_by_name():
    # A hand-written command file: `login` passes the gate as the word of a
    # plain login, so only the body can see that it is not a method.
    ide_globals = an_ide(allowed=("login",))
    result = log_in(ide_globals, method="login", yes=True)
    assert not result["ok"]
    assert session_of(ide_globals).calls == []
    assert "--method login" in result["summary"]
    assert "nothing was done" in result["summary"]


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
    assert result["data"]["methods"] == ["download"]
    assert device.connected is False


class Silent(Device):
    """A controller that does not answer."""

    def connect(self):
        raise IOError("no route to the device")


def test_a_controller_that_does_not_answer_is_not_said_to_need_a_download():
    device = Silent()
    ide_globals = an_ide(device=device)
    result = log_in(ide_globals)
    assert not result["ok"]
    assert logins(ide_globals) == []
    assert "did not answer" in result["summary"]
    assert result["data"]["methods"] == []
    assert "--method" not in result["summary"]
    assert device.connected is False


class Flaky(Device):
    """A controller that answers and lists its application, but whose file
    fetch fails, as a dropped link does."""

    def upload_file(self, remote, local, overwrite):
        self.uploaded.append(remote)
        raise IOError("the transfer was aborted")


def test_a_fetch_that_failed_is_not_said_to_need_a_download():
    # Only a controller found holding another program, or none, needs one:
    # this one may hold exactly this copy's download.
    device = Flaky()
    ide_globals = an_ide(device=device)
    result = log_in(ide_globals)
    assert not result["ok"]
    assert logins(ide_globals) == []
    assert "could not be fetched" in result["summary"]
    assert result["data"]["methods"] == []
    assert "--method" not in result["summary"]
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

    def create_boot_application(self):
        self.log.append("create_boot_application")
        Session.create_boot_application(self)


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
    assert any("given no credentials" in note
               for note in result["data"]["notes"])


def test_without_credentials_the_notes_say_none_were_given():
    ide_globals = an_ide()
    result = log_in(ide_globals)
    assert result["ok"], result["summary"]
    assert ide_globals["online"].credentials is None
    notes = [n for n in result["data"]["notes"] if "credentials" in n]
    # Only what this command had: the IDE may still hold an earlier login.
    assert any("this command was given no credentials" in n for n in notes)
    assert not any("controller gets" in n for n in notes)


def test_the_ide_s_own_environment_is_not_the_caller_s(monkeypatch):
    # Design R4: in the watcher the login comes from the caller only.
    monkeypatch.setenv("CDS_DEV_USER", "ide-side")
    monkeypatch.setenv("CDS_DEV_PASS", "ide-side-secret")
    ide_globals = an_ide()
    result = log_in(ide_globals)
    assert result["ok"], result["summary"]
    assert ide_globals["online"].credentials is None
    assert "ide-side" not in json.dumps(result)


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
    ide_globals = an_ide(allowed=("online_change",),
                         application=Watched(log))
    online = LoggedOnline(log)
    ide_globals["online"] = online
    result = log_in(ide_globals, method="online_change", yes=True)
    assert result["ok"], result["summary"]
    assert log.index("is_online_change_possible") < log.index("login")
    assert [c[1] for c in online.session.calls if c[0] == "login"] == [
        OnlineChangeOption.Force]
    assert plc_session.ONLINE_CHANGE == "Force"


# -- plc login --method (design 5.2, 5.3) --------------------------------------

def changed_copy(possible=True):
    application = Application()
    application.is_uptodate = False
    application.is_online_change_possible = possible
    return application


def by(method, application=None, allowed=None, **more):
    """An IDE that allows `method`, and the result of logging in by it."""
    ide_globals = an_ide(allowed=allowed or (method,), application=application)
    args = {"method": method, "yes": True}
    args.update(more)
    return ide_globals, press(ide_globals, "login", args)


@pytest.mark.parametrize("method", ["download", "online_change"])
def test_without_yes_a_method_asks_and_nothing_logs_in(method, monkeypatch):
    runs = counted_script_runs(monkeypatch)
    ide_globals = an_ide(allowed=(method,), application=changed_copy())
    outcome = press(ide_globals, "login", {"method": method})
    assert outcome.needs is not None and outcome.needs.arg == "yes"
    assert session_of(ide_globals).calls == []
    # Asked outside the script run: the question is a BaseException, which
    # the nested run's parking catches nothing of (ide_private).
    assert runs == []


@pytest.mark.parametrize("method", ["download", "online_change"])
def test_saying_no_to_a_method_changes_nothing(method):
    ide_globals, outcome = by(method, changed_copy(), yes=False)
    assert outcome.needs is None and not outcome.ok()
    assert "cancelled" in outcome.result["summary"]
    assert session_of(ide_globals).calls == []


def test_the_download_question_says_it_leaves_the_application_stopped():
    ide_globals = an_ide(allowed=("download",))
    outcome = press(ide_globals, "login", {"method": "download"})
    asked = outcome.needs.question.lower()
    assert "stopped" in asked and "boot application" in asked
    assert "plc run -y" in asked


def test_the_online_change_question_says_it_keeps_the_application_running():
    ide_globals = an_ide(allowed=("online_change",))
    outcome = press(ide_globals, "login", {"method": "online_change"})
    asked = outcome.needs.question.lower()
    assert "online" in asked and "keeps" in asked


def test_download_logs_in_never_and_writes_the_boot_application():
    ide_globals = an_ide(allowed=("download",), application=changed_copy())
    session_of(ide_globals).states_after_login = {"never": "stop"}
    result = log_in(ide_globals, method="download", yes=True)
    assert result["ok"], result["summary"]
    assert session_of(ide_globals).calls == [
        ("login", "never", False), ("create_boot_application",)]
    data = result["data"]
    assert data["changed"] == "download"
    assert data["state"] == "stop"
    assert data["boot_application"] is True
    assert data["logged_in"] is True
    assert "downloaded in full" in result["summary"]


def test_download_downloads_even_when_nothing_differs():
    ide_globals, outcome = by("download")
    assert outcome.ok(), outcome.result["summary"]
    assert session_of(ide_globals).calls == [
        ("login", "never", False), ("create_boot_application",)]
    assert outcome.result["data"]["changed"] == "download"


@pytest.mark.parametrize("method", ["download", "online_change"])
def test_no_boot_app_skips_it(method):
    ide_globals, outcome = by(method, changed_copy(), no_boot_app=True)
    assert outcome.ok(), outcome.result["summary"]
    assert ("create_boot_application",) not in session_of(ide_globals).calls
    assert outcome.result["data"]["boot_application"] is False


def test_online_change_that_is_not_possible_touches_nothing():
    path = plc_fakes.recorded()
    ide_globals, outcome = by("online_change", changed_copy(possible=False))
    result = outcome.result
    assert not result["ok"]
    assert outcome.needs is None
    assert session_of(ide_globals).calls == []
    assert "--method download" in result["summary"]
    assert "nothing was done" in result["summary"]
    assert result["data"]["online_change_possible"] is False
    assert result["data"]["methods"] == ["download"]
    assert plc_crc.read_records(path).get(plc_fakes.CONTROLLER)


def test_online_change_keeps_the_running_state():
    ide_globals, outcome = by("online_change", changed_copy())
    result = outcome.result
    assert result["ok"], result["summary"]
    assert session_of(ide_globals).calls == [
        ("login", getattr(OnlineChangeOption, plc_session.ONLINE_CHANGE),
         False),
        ("create_boot_application",)]
    assert result["data"]["state"] == "run"
    assert result["data"]["changed"] == "online_change"
    assert result["data"]["boot_application"] is True
    assert "changed online" in result["summary"]


def test_online_change_with_nothing_different_writes_no_boot_application():
    path = plc_fakes.recorded()
    ide_globals, outcome = by("online_change")
    result = outcome.result
    assert result["ok"], result["summary"]
    assert session_of(ide_globals).calls == [
        ("login", getattr(OnlineChangeOption, plc_session.ONLINE_CHANGE),
         False)]
    assert result["data"]["changed"] == "nothing"
    assert result["data"]["boot_application"] is False
    assert "nothing on the controller changed" in result["summary"]
    # Nothing moved, so what the record says is still true.
    assert plc_crc.read_records(path).get(plc_fakes.CONTROLLER)


@pytest.mark.parametrize("method", ["download", "online_change"])
def test_a_method_while_logged_in_says_log_out_first(method):
    ide_globals = an_ide(allowed=(method,), application=changed_copy())
    session_of(ide_globals).is_logged_in = True
    result = log_in(ide_globals, method=method, yes=True)
    assert not result["ok"]
    assert session_of(ide_globals).calls == []
    assert "log out first" in result["summary"]
    assert "plc logout" in result["summary"]


def test_a_download_that_raises_says_the_controller_may_be_stopped():
    ide_globals = an_ide(allowed=("download",))
    session_of(ide_globals).refuse_login = "the transfer was aborted"
    result = log_in(ide_globals, method="download", yes=True)
    assert not result["ok"]
    assert ("the download did not complete, and the controller may now be "
            "stopped or partly written") in result["summary"]
    assert "the transfer was aborted" in result["summary"]


def test_a_refused_online_change_is_never_said_to_have_downloaded():
    ide_globals = an_ide(allowed=("online_change",),
                         application=changed_copy())
    session_of(ide_globals).refuse_login = "Login failed..."
    result = log_in(ide_globals, method="online_change", yes=True)
    assert not result["ok"]
    assert "online change did not complete" in result["summary"]
    assert "Login failed..." in result["summary"]
    assert ("create_boot_application",) not in session_of(ide_globals).calls


def test_another_client_refuses_a_method_too():
    ide_globals = an_ide(allowed=("download",))
    session_of(ide_globals).refuse_login = (
        "Login failed: the user is already logged in from another client")
    result = log_in(ide_globals, method="download", yes=True)
    assert not result["ok"]
    assert "another client is logged in" in result["summary"]


def test_a_boot_application_that_fails_says_what_a_restart_brings_back():
    ide_globals = an_ide(allowed=("download",))
    session = session_of(ide_globals)

    def refuses():
        session.calls.append(("create_boot_application",))
        raise IOError("no space left on the controller")
    session.create_boot_application = refuses
    result = log_in(ide_globals, method="download", yes=True)
    assert not result["ok"]
    assert "boot application was not written" in result["summary"]
    assert "no space left" in result["summary"]
    assert result["data"]["boot_application"] is False
    # Read back, failure or not: the login before it did happen.
    assert result["data"]["logged_in"] is True


# -- the CRC record (design 5.6, R5) -------------------------------------------

def answer_now(path, device):
    """What a plc connect would answer for the controller, from the record."""
    plc = plc_crc.crc_field(device.crc)
    return plc_crc.judge(plc_crc.read_records(path).get(plc_fakes.CONTROLLER),
                         plc, None)[0]


@pytest.mark.parametrize("method", ["download", "online_change"])
def test_a_watcher_download_never_leaves_a_stale_match(method):
    # The worst case: the record says MATCH for the CRC the controller holds,
    # and the change leaves that CRC where it was (an online change without
    # a boot application, research 17.7).
    device = Device()
    path = plc_fakes.recorded(plc_crc=plc_crc.crc_field(device.crc))
    assert answer_now(path, device) == plc_crc.MATCH
    ide_globals = an_ide(allowed=(method,), application=changed_copy())
    ide_globals["online"] = Online(device=device,
                                   gateways=[plc_fakes.Gateway()])
    result = log_in(ide_globals, method=method, yes=True, no_boot_app=True)
    assert result["ok"], result["summary"]
    assert answer_now(path, device) != plc_crc.MATCH
    assert any(plc_fakes.CONTROLLER in note for note in result["data"]["notes"])


def test_a_download_that_raises_has_already_forgotten_the_record():
    path = plc_fakes.recorded()
    ide_globals = an_ide(allowed=("download",))
    session_of(ide_globals).refuse_login = "the transfer was aborted"
    assert not log_in(ide_globals, method="download", yes=True)["ok"]
    assert plc_crc.read_records(path) == {}


def test_a_record_that_cannot_be_cleared_stops_the_download(monkeypatch):
    plc_fakes.recorded()

    def refuses(path, data):
        raise IOError("the file is open elsewhere")
    monkeypatch.setattr(plc_crc.ipc, "write_json", refuses)
    ide_globals = an_ide(allowed=("download",))
    result = log_in(ide_globals, method="download", yes=True)
    assert not result["ok"]
    assert session_of(ide_globals).calls == []
    assert "nothing was done" in result["summary"]


# -- the same two rules, for a method -------------------------------------------

def test_a_method_runs_inside_one_script_run(monkeypatch):
    runs = counted_script_runs(monkeypatch)
    ide_globals, outcome = by("download")
    assert outcome.ok(), outcome.result["summary"]
    assert len(runs) == 1


def test_credentials_are_handed_over_before_the_boot_application():
    log = []
    ide_globals = an_ide(allowed=("online_change",),
                         application=changed_copy())
    ide_globals["online"] = LoggedOnline(log)
    outcome = press(ide_globals, "login",
                    {"method": "online_change", "yes": True,
                     "credentials": dict(LOGIN)})
    assert outcome.ok(), outcome.result["summary"]
    online_calls = ONLINE_CALLS + ("create_boot_application",)
    called = [i for i, event in enumerate(log) if event in online_calls]
    assert [log[i] for i in called] == [
        "create_online_application", "login", "create_boot_application"]
    for i in called:
        assert log[i - 2:i] == ["dialog off", "credentials"], (i, log)
    written = (json.dumps(outcome.result) + outcome.stdout_tail
               + repr(outcome.messages))
    assert SECRET not in written
