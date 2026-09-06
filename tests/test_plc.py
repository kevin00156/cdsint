# -*- coding: utf-8 -*-
"""The two gates in front of a controller, and the answer they guard.

`plc download` is the one command in cdsint that changes a machine, so it is
the one command with a permission layer in front of it (SPEC D8, 6.5): the
project property cds-sync-plc says whether this project allows the action at
all, and -y says the caller means this call. Neither can stand in for the
other, and both have to hold before anything logs in — a check that runs
inside the body it guards has already let the body start.

What comes back is a CRC comparison, and that is the whole point of the pair
(SPEC 6.6) — but not the obvious comparison. An offline boot application and
the controller's are different artefacts and never match, and the offline one
moves every run besides; engine/plc_crc.py holds the bench measurements that
say so. What is compared is the CRC the controller holds now against the one
a download from this project left there. MATCH is the only answer that
passes, because a caller reading the exit code has to be able to tell "it is
still running what I put there" from "it might be running anything".

Everything here runs against stand-in IDE objects. The controller itself is
a bench test and needs a person (the plan's phase 3).
"""
import io
import os
import sys
import types

import pytest

from cds.core import commands
from cds.core import settings
from cds.ide import entries, permit, silent
from cdsint import cli, flags
from cdsint.exits import EXIT_DENIED, EXIT_FAILED, EXIT_OK
from engine import plc_crc as plc_crc_module

ENGINE_ROOT = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "engine")
PLC_BODY = os.path.join(ENGINE_ROOT, "entry_plc.py")

DEVICE_GUID = "225bfe47-7336-4dbc-9419-4105a7c831fa"

# Three .crc files that agree everywhere except the four bytes that matter,
# which is what makes the header worth skipping. A is what the project builds
# to, B is what the controller held before, C is what a download leaves on it:
# on a real bench all three differ, and the second and third always do.
HEADER = b"\x00\x01\x02\x03"
CRC_A = HEADER + b"\xDE\xAD\xBE\xEF" + b"Application\x00"
CRC_B = HEADER + b"\x11\x22\x33\x44" + b"Application\x00"
CRC_C = HEADER + b"\x55\x66\x77\x88" + b"Application\x00"

# Where the fake project's file sits. Set for each test by the `workspace`
# fixture, because a download writes its record beside the project and a test
# that used a made-up path would write it to a made-up place on the real disk.
PROJECT_PATH = None


# --------------------------------------------------------------------------
# Stand-ins for the IDE
# --------------------------------------------------------------------------

class Node(object):
    """An object in the project tree."""

    def __init__(self, name, type_guid="not-a-device"):
        self._name = name
        self.type = type_guid
        self.gateway_set_to = None

    def get_name(self):
        return self._name

    def get_children(self, recursive=False):
        return []

    def set_gateway_and_ip_address(self, gateway, address, port):
        self.gateway_set_to = (gateway, address, port)


class Application(object):
    """The project's active application: what a download is a download of.

    It has no create_boot_application of its own any more. The offline call
    that writes one to a path was how the verdict used to be reached, and
    engine/plc_crc.py records why that could not work; a fake that still
    offered it would keep the idea alive in the one place nobody would look.
    """


class Info(object):
    def __init__(self, values):
        self.values = values


class Project(object):
    def __init__(self, values, children, path, application=None):
        self._values = values
        self._children = children
        self.path = path
        self.active_application = application

    def get_project_info(self):
        return Info(self._values)

    def get_children(self, recursive=False):
        return list(self._children)

    def get_name(self):
        return "FakeProject"


class Projects(object):
    def __init__(self, primary):
        self.primary = primary


class RemoteFile(object):
    def __init__(self, name, size=12, is_directory=False):
        self.name = name
        self.size = size
        self.is_directory = is_directory


class Device(object):
    """A live device connection: lists files and hands them over."""

    def __init__(self, crc=CRC_B, archive=True):
        self.crc = crc
        self.archive = archive
        self.connected = False
        self.uploaded = []

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def get_file_list_of_directory(self, directory):
        return [RemoteFile("Application.crc"), RemoteFile("Application.app")]

    def upload_file(self, remote, local, overwrite):
        self.uploaded.append(remote)
        if self.crc is None:
            raise IOError("Could not find a part of the path: " + remote)
        with open(local, "wb") as handle:
            handle.write(self.crc)

    def upload_source(self, local):
        if not self.archive:
            raise IOError("no source archive on this controller")
        with open(local, "wb") as handle:
            handle.write(b"an archive")


class Session(object):
    """An online application: this is the object that downloads.

    create_boot_application is what puts a boot application on the controller,
    so it is what changes the controller's CRC. `writes` is the run of values
    it leaves there, one per download; an empty one is a session that returns
    without error having written nothing, which is the failure the read-back
    is for.
    """

    def __init__(self, device=None, writes=None):
        self.calls = []
        self.application_state = "run"
        self.device = device
        self.writes = [CRC_C] if writes is None else list(writes)

    def login(self, option, delete_foreign_apps):
        self.calls.append(("login", option, delete_foreign_apps))

    def create_boot_application(self):
        self.calls.append(("create_boot_application",))
        if self.device is not None and self.writes:
            self.device.crc = self.writes.pop(0)

    def start(self):
        self.calls.append(("start",))

    def logout(self):
        self.calls.append(("logout",))


class Online(object):
    """The CODESYS `online` global, shaped like ScriptEngine 4.2.0.0.

    `auth_fallback_modes` is a settable property there and there is no
    `set_auth_fallback_modes` method at all. This fake had the method and not
    the property, so 61 tests vouched for a call no IDE has, and the bench
    found out the hard way: the dialog was never switched off and four runs
    hung until they were killed. A property here means an assignment that
    lands on a plain attribute cannot pass for the real thing.
    """

    def __init__(self, device=None, gateways=()):
        self.device = device if device is not None else Device()
        self.gateways = list(gateways)
        self.session = Session(device=self.device)
        self._fallback = "never set"
        self.credentials = None

    @property
    def auth_fallback_modes(self):
        return self._fallback

    @auth_fallback_modes.setter
    def auth_fallback_modes(self, kinds):
        self._fallback = kinds

    def set_default_credentials(self, user, password):
        self.credentials = (user, password)

    def create_online_device(self, node):
        return self.device

    def create_online_application(self, application):
        return self.session


class NoSwitch(Online):
    """An IDE whose API offers neither spelling.

    Nothing has confirmed such an IDE exists — ScriptEngine 4.0.0.0 (Lenze
    3.24, Delta 1.10) has not been looked at. It is a fake for the rule
    rather than for a machine: whatever cannot switch the dialog off must
    not be connected to, because under --noUI that is a hang.
    """

    @property
    def auth_fallback_modes(self):
        raise AttributeError("auth_fallback_modes")

    @auth_fallback_modes.setter
    def auth_fallback_modes(self, kinds):
        raise AttributeError("auth_fallback_modes")

    def set_auth_fallback_modes(self, kinds):
        raise AttributeError("set_auth_fallback_modes")


class Gateway(object):
    def __init__(self, name="Gateway-1"):
        self.name = name
        self.asked = []

    def find_address_by_ip(self, address, port):
        self.asked.append((address, port))
        return "0000.0001"


class CredentialSourceKind(object):
    """The real enum's member really is called None, hence getattr."""


setattr(CredentialSourceKind, "None", "no-dialog")


class OnlineChangeOption(object):
    Never = "never"


class FakeSystem(object):
    def __init__(self):
        self.ui = "the real ui, which must survive"


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fake_codesys_ui():
    """The dialog module, which needs clr and so cannot be the real one.

    cds/ide/silent.py swaps its three dialog functions for stand-ins that
    answer from the command's flags, and refuses to run a body it cannot do
    that to — so a fake has to be here for the download confirmation to
    behave the way it does inside an IDE.
    """
    module = types.ModuleType("engine.codesys_ui")

    def opened(*args, **kwargs):
        raise AssertionError("a real message box was opened")

    for name in ("ask_yes_no", "ask_yes_no_cancel",
                 "show_sync_folder_dialog"):
        setattr(module, name, opened)
    sys.modules["engine.codesys_ui"] = module
    yield module
    # popped, not deleted: entries.run() empties sys.modules of the whole
    # engine before it presses a body, so this may already be gone.
    sys.modules.pop("engine.codesys_ui", None)


@pytest.fixture(autouse=True)
def keep_the_engine_loaded(monkeypatch):
    """Stop entries.run() emptying sys.modules of the engine.

    It does that so a watcher picks up an edited engine without the IDE
    being restarted, which is right inside an IDE and wrong in a test run:
    other test modules hold references to engine modules, and a reload gives
    engine/unhandled.py a second register that nothing they hold can see.
    The tests here that go through entries.run() are about the gate in front
    of the body, not about the module cache behind it.
    """
    monkeypatch.setattr(entries, "forget_engine", lambda: None)


@pytest.fixture(autouse=True)
def workspace(tmp_path, monkeypatch):
    """Keep everything a run writes out of the real filesystem.

    Two places, not one: the .app, .crc and archive go under TEMP, and the
    record of a download goes beside the project — so the fake project has to
    live somewhere real and disposable too.
    """
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(sys.modules[__name__], "PROJECT_PATH",
                        os.path.join(str(tmp_path), "Line.project"))
    return tmp_path


def ide(allowed=("connect", "download"), device=None, application=None,
        children=None, gateways=()):
    """The IDE globals a plc body reads, with the settings file written.

    The list goes on disk rather than into the fake project, because that is
    where cds/ide/permit.py reads it from now: the file beside the .project
    (SPEC D10). `allowed=None` is a project nobody has set up at all.
    """
    if allowed is not None:
        settings.write(settings.path_for(PROJECT_PATH), {"plc": list(allowed)})
    values = {}
    application = application if application is not None else Application()
    children = children if children is not None else [Node("Device",
                                                           DEVICE_GUID)]
    project = Project(values, children, PROJECT_PATH, application)
    online = Online(device=device, gateways=gateways)
    return {"system": FakeSystem(), "projects": Projects(project),
            "online": online, "CredentialSourceKind": CredentialSourceKind,
            "OnlineChangeOption": OnlineChangeOption}


def recorded(plc_crc="11223344", controller=plc_crc_module.PROJECT_GATEWAY):
    """Write the record a download would have left, and hand back its path."""
    path = plc_crc_module.record_path(PROJECT_PATH)
    plc_crc_module.remember(path, controller,
                            {"plc_crc": plc_crc, "device": "Device",
                             "downloaded_at": "2026-09-06T10:00:00"})
    return path


def press(ide_globals, entry, args):
    """Run one plc body the way cds/ide/entries.py does, gate included."""
    return entries.run(ide_globals, "plc " + entry, args)


# --------------------------------------------------------------------------
# The property: what a person wrote in the IDE
# --------------------------------------------------------------------------

def test_no_settings_file_allows_nothing():
    assert permit.granted(ide(allowed=None)["projects"]) == []


def test_one_word_allows_one_action():
    assert permit.granted(ide(allowed=["connect"])["projects"]) == ["connect"]


def test_both_words_allow_both_in_the_order_spec_lists_them():
    assert permit.granted(ide(allowed=["download", "connect"])["projects"])         == ["connect", "download"]


def test_case_is_a_persons_typing_not_a_decision():
    assert permit.granted(ide(allowed=["DOWNLOAD"])["projects"]) == ["download"]


def test_a_settings_file_that_cannot_be_read_allows_nothing():
    # The command itself reads the same file a moment later and reports the
    # typo in full (SPEC 4.4); what must not happen here is the gate opening
    # because the file could not be parsed.
    projects = ide(allowed=None)["projects"]
    with io.open(settings.path_for(PROJECT_PATH), "w",
                 encoding="utf-8") as handle:
        handle.write(u'{"plc": ["downlaod"]}')
    assert permit.granted(projects) == []


def test_the_refusal_says_which_file_and_what_to_write():
    said = permit.refusal(ide(allowed=["connect"])["projects"], "download")
    assert "plc" in said
    assert '["connect", "download"]' in said          # what to set it to
    assert settings.path_for(PROJECT_PATH) in said    # where


# --------------------------------------------------------------------------
# The first gate: the engine is never reached
# --------------------------------------------------------------------------

def test_a_project_that_allows_nothing_refuses_download_before_any_login():
    ide_globals = ide(allowed=None)
    outcome = press(ide_globals, "download", {"yes": True})
    assert outcome.denied == {"file": settings.path_for(PROJECT_PATH),
                              "key": "plc", "action": "download"}
    assert not outcome.ok()
    assert ide_globals["online"].session.calls == []


def test_the_refused_command_does_not_even_load_the_engine(monkeypatch):
    # Stronger than "login was not called": the body is never run at all, so
    # there is no path through the engine for a future edit to open up.
    ran = []
    monkeypatch.setattr(silent, "run",
                        lambda *args, **kwargs: ran.append(args))
    press(ide(allowed=None), "download", {"yes": True})
    assert ran == []


def test_allowing_download_does_not_allow_connect():
    # Two names, two decisions. Reading a controller and writing to one are
    # not the same permission, whichever way round somebody expects.
    outcome = press(ide(allowed=["download"]), "connect", {})
    assert outcome.denied["action"] == "connect"


def test_an_allowed_command_gets_through_to_the_engine(monkeypatch):
    ran = []
    monkeypatch.setattr(silent, "run",
                        lambda *args, **kwargs: ran.append(args[2]))
    press(ide(allowed=["connect"]), "connect", {})
    assert ran == ["connect"]


def test_the_other_commands_are_not_gated(monkeypatch):
    ran = []
    monkeypatch.setattr(silent, "run",
                        lambda *args, **kwargs: ran.append(args[2]))
    entries.run(ide(allowed=None), "export", {})
    assert ran == ["main"]


def test_a_refusal_is_exit_5_and_a_failure_is_exit_1():
    denied = {"ok": False, "denied": permit.record(None, "download")}
    assert cli.exit_code(denied) == EXIT_DENIED
    assert cli.exit_code({"ok": False, "error": "it broke"}) == EXIT_FAILED
    assert cli.exit_code({"ok": True}) == EXIT_OK


class FakeRunner(object):
    """Answers run(steps) with one record, and remembers what it was asked."""

    def __init__(self, record):
        self.record = record
        self.asked = []

    def describe(self):
        return "a fake IDE"

    def sync_dir(self):
        return os.path.join("C:" + os.sep, "tmp", "sync")

    def run(self, steps):
        self.asked = steps
        return [dict(self.record, command=steps[0][0])]


def drive(monkeypatch, record):
    runner = FakeRunner(record)
    monkeypatch.setattr(cli, "make_runner", lambda ns: runner)
    return runner


def test_a_project_that_forbids_it_comes_back_as_exit_5(monkeypatch, capsys):
    projects = ide(allowed=None)["projects"]
    said = permit.refusal(projects, "download")
    drive(monkeypatch, {"ok": False, "error": said,
                        "denied": permit.record(projects, "download")})
    code = cli.main(["plc", "download", "-y", "--project", "P", "--install",
                     "I", "--sync-dir", "S"])
    assert code == EXIT_DENIED
    assert "plc" in capsys.readouterr().err


def test_a_download_with_no_yes_comes_back_as_exit_1(monkeypatch, capsys):
    # Not 5: the settings file allows it and a flag would fix this, which is a
    # different next move for whoever is reading the code.
    question = "Confirm PLC Download: ..."
    drive(monkeypatch, {"ok": False, "error": question, "denied": None,
                        "needs_input": {"question": question, "arg": "yes"}})
    code = cli.main(["plc", "download", "--project", "P", "--install", "I",
                     "--sync-dir", "S"])
    assert code == EXIT_FAILED
    assert "--yes" in capsys.readouterr().err


def test_a_match_comes_back_as_exit_0(monkeypatch):
    runner = drive(monkeypatch, {"ok": True, "data": {"crc": "MATCH"},
                                 "messages": []})
    assert cli.main(["plc", "connect", "--project", "P", "--install", "I",
                     "--sync-dir", "S"]) == EXIT_OK
    assert runner.asked[0][0] == "plc connect"


def test_the_refusal_survives_the_trip_through_a_result_record():
    # exit 5 is decided from the record the CLI reads back, so the field has
    # to be in it — both forms write results through this one function.
    record = commands.new_result({"id": "1", "command": "plc download"},
                                 False, error="nope",
                                 denied=permit.record(None, "download"))
    assert cli.exit_code(record) == EXIT_DENIED


# --------------------------------------------------------------------------
# The second gate: -y
# --------------------------------------------------------------------------

def test_without_yes_the_download_asks_and_nothing_logs_in():
    ide_globals = ide(allowed=["download"])
    outcome = silent.run(ide_globals, PLC_BODY, "download", {})
    assert outcome.needs is not None and outcome.needs.arg == "yes"
    assert ide_globals["online"].session.calls == []


def test_the_question_says_what_the_download_will_do():
    outcome = silent.run(ide(allowed=["download"]), PLC_BODY, "download", {})
    asked = outcome.needs.question.lower()
    for promised in ("stop", "boot application", "start"):
        assert promised in asked


def test_connect_never_asks_for_yes():
    # Reading a controller changes nothing, so a confirmation would be a
    # question with one useful answer.
    outcome = silent.run(ide(allowed=["connect"]), PLC_BODY, "connect", {})
    assert outcome.needs is None


def test_with_yes_the_download_is_a_full_one_and_writes_a_boot_application():
    ide_globals = ide(allowed=["download"])
    silent.run(ide_globals, PLC_BODY, "download", {"yes": True})
    calls = ide_globals["online"].session.calls
    assert [name for name, _rest in [(c[0], c[1:]) for c in calls]] == [
        "login", "create_boot_application", "start", "logout"]
    # Never an online change: the point of a download from a pipeline is that
    # every initialisation runs again.
    assert calls[0][1:] == (OnlineChangeOption.Never, False)


def test_saying_no_outright_is_not_the_same_as_not_being_asked():
    ide_globals = ide(allowed=["download"])
    outcome = silent.run(ide_globals, PLC_BODY, "download", {"yes": False})
    assert outcome.needs is None and not outcome.ok()
    assert "cancelled" in outcome.error_text().lower()
    assert ide_globals["online"].session.calls == []


# --------------------------------------------------------------------------
# Only the --project form (SPEC D8)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("argv", [
    ["plc", "connect", "--target", "X"],
    ["plc", "download", "-y", "--target", "X"],
])
def test_the_watcher_form_is_refused_with_the_reason(argv, capsys):
    with pytest.raises(SystemExit) as raised:
        cli.main(argv)
    assert raised.value.code == 2
    said = capsys.readouterr().err
    assert "online session" in said and "D8" in said


def test_neither_form_named_is_refused_the_same_way(capsys):
    with pytest.raises(SystemExit) as raised:
        cli.main(["plc", "connect"])
    assert raised.value.code == 2
    assert "--project" in capsys.readouterr().err


def test_the_project_form_no_longer_has_to_say_where_the_st_files_are():
    # --sync-dir was compulsory while a copy of a .project carried the
    # original's sync folder inside it. The settings live beside the project
    # now, so a copy of the .project alone carries nothing (SPEC 4.2), and
    # the parser lets the command through to look for a settings file.
    parsed = flags.build_parser().parse_args(
        ["plc", "connect", "--project", "P", "--install", "I"])
    assert parsed.sync_dir is None


def test_the_watcher_will_not_run_a_plc_command():
    assert "plc connect" not in entries.COMMANDS
    assert "plc download" not in entries.COMMANDS
    assert set(entries.WATCHER_REFUSES) == {"plc connect", "plc download"}


def test_the_watcher_refuses_by_name_rather_than_pretending_not_to_know():
    # A hand-written command file is the way one gets there, and "unknown
    # command" would send the reader looking for a typo.
    for reason in entries.WATCHER_REFUSES.values():
        assert "--project" in reason and "D8" in reason


def test_the_two_actions_reach_two_different_functions():
    assert entries.SCRIPTS["plc connect"] == ("entry_plc.py", "connect")
    assert entries.SCRIPTS["plc download"] == ("entry_plc.py", "download")


def test_the_cli_spells_the_action_into_the_command_name():
    parsed = flags.build_parser().parse_args(
        ["plc", "download", "-y", "--project", "P", "--install", "I",
         "--sync-dir", "S"])
    assert flags.wire_name(parsed) == "plc download"
    assert flags.command_args(parsed) == {"yes": True, "gateway": None,
                                        "port": None}


def test_the_gateway_flags_reach_the_body():
    parsed = flags.build_parser().parse_args(
        ["plc", "connect", "--project", "P", "--install", "I", "--sync-dir",
         "S", "--gateway", "192.168.1.5", "--port", "11740"])
    assert flags.command_args(parsed) == {"yes": None, "gateway": "192.168.1.5",
                                        "port": 11740}


# --------------------------------------------------------------------------
# The answer: the CRC comparison (SPEC 6.6)
# --------------------------------------------------------------------------

def crc_of(outcome):
    return outcome.result["data"]["crc"]


def test_a_controller_still_holding_what_was_downloaded_is_a_match():
    recorded(plc_crc="11223344")
    ide_globals = ide(allowed=["connect"], device=Device(crc=CRC_B))
    outcome = silent.run(ide_globals, PLC_BODY, "connect", {})
    assert crc_of(outcome) == "MATCH"
    assert outcome.ok()


def test_a_connect_with_nothing_ever_downloaded_is_unknown_not_a_match():
    # The bench found this the hard way round: the old comparison built a
    # boot application and held it against the controller's, and those are
    # different artefacts, so the answer was DIFFERENT every time and carried
    # no information. Having nothing to compare against must say so.
    ide_globals = ide(allowed=["connect"], device=Device(crc=CRC_B))
    outcome = silent.run(ide_globals, PLC_BODY, "connect", {})
    assert crc_of(outcome) == "UNKNOWN"
    assert not outcome.ok()
    assert "download -y" in outcome.result["summary"]


def test_a_controller_somebody_else_loaded_is_different_and_fails():
    # The finding is the point of the command, and nothing wraps these two
    # the way verify wraps compare — so the exit code has to be the verdict.
    recorded(plc_crc="11223344")
    ide_globals = ide(allowed=["connect"], device=Device(crc=CRC_C))
    outcome = silent.run(ide_globals, PLC_BODY, "connect", {})
    assert crc_of(outcome) == "DIFFERENT"
    assert not outcome.ok()
    assert "loaded with something else since" in outcome.result["summary"]


def test_editing_the_project_does_not_move_this_verdict():
    # The narrow claim, held to deliberately. This command answers "does the
    # controller still hold what cdsint put there", and an edit nobody
    # downloaded does not change that. The wider question -- is the project
    # what the disk says -- is compare's and verify's, which read every
    # object; answering it from here would mean guessing from a number that
    # moves on its own (engine/plc_crc.py).
    recorded(plc_crc="11223344")
    ide_globals = ide(allowed=["connect"], device=Device(crc=CRC_B))
    outcome = silent.run(ide_globals, PLC_BODY, "connect", {})
    assert crc_of(outcome) == "MATCH" and outcome.ok()


def test_the_record_the_verdict_used_is_in_the_report():
    # A verdict a reader cannot audit is a verdict they have to trust.
    recorded(plc_crc="11223344")
    ide_globals = ide(allowed=["connect"], device=Device(crc=CRC_B))
    data = silent.run(ide_globals, PLC_BODY, "connect", {}).result["data"]
    assert data["recorded"]["plc_crc"] == "11223344"
    assert data["recorded"]["downloaded_at"] == "2026-09-06T10:00:00"
    assert data["controller"] == "project"


def test_a_record_for_another_controller_is_not_this_controllers():
    # Same working copy, two benches: the record for A must not answer for B.
    recorded(plc_crc="11223344", controller="127.0.0.1:11740")
    ide_globals = ide(allowed=["connect"], device=Device(crc=CRC_B),
                      gateways=[Gateway()])
    outcome = silent.run(ide_globals, PLC_BODY, "connect",
                         {"gateway": "127.0.0.1", "port": 11741})
    assert crc_of(outcome) == "UNKNOWN"


def test_only_the_identity_bytes_are_read():
    # Two files that share a header and differ in the field must not read the
    # same, and that is the whole reason the first four bytes are skipped.
    assert CRC_A[:4] == CRC_B[:4]
    recorded(plc_crc="DEADBEEF")
    ide_globals = ide(allowed=["connect"], device=Device(crc=CRC_B))
    outcome = silent.run(ide_globals, PLC_BODY, "connect", {})
    assert outcome.result["data"]["plc_crc"] == "11223344"
    assert crc_of(outcome) == "DIFFERENT"


def test_a_controller_with_nothing_loaded_is_unknown_not_a_match():
    # "cannot tell" reading the same as "matches" is the silent failure this
    # whole codebase exists to keep out (SPEC goal 6).
    ide_globals = ide(allowed=["connect"], device=Device(crc=None))
    outcome = silent.run(ide_globals, PLC_BODY, "connect", {})
    assert crc_of(outcome) == "UNKNOWN"
    assert not outcome.ok()
    assert "Application.crc" in outcome.result["summary"]


def test_a_download_reports_the_crc_it_checked_afterwards():
    ide_globals = ide(allowed=["download"], device=Device(crc=CRC_B))
    outcome = silent.run(ide_globals, PLC_BODY, "download", {"yes": True})
    assert crc_of(outcome) == "MATCH" and outcome.ok()
    assert outcome.result["data"]["plc_crc"] == "55667788"


def test_a_download_writes_down_what_it_left_there():
    # This is the whole basis of a later connect's answer: nothing built
    # locally reproduces what the controller holds, so what cdsint itself put
    # there, recorded at the moment it put it, is the only reference.
    ide_globals = ide(allowed=["download"], device=Device(crc=CRC_B))
    silent.run(ide_globals, PLC_BODY, "download", {"yes": True})
    written = plc_crc_module.read_records(
        plc_crc_module.record_path(PROJECT_PATH))["project"]
    assert written["plc_crc"] == "55667788"
    assert written["device"] == "Device"


def test_a_download_then_a_connect_is_a_match():
    # The pair the bench runs, in one test: nothing is set up by hand.
    silent.run(ide(allowed=["connect", "download"], device=Device(crc=CRC_B)),
               PLC_BODY, "download", {"yes": True})
    after = ide(allowed=["connect", "download"], device=Device(crc=CRC_C))
    outcome = silent.run(after, PLC_BODY, "connect", {})
    assert crc_of(outcome) == "MATCH" and outcome.ok()


def test_a_download_that_did_not_take_is_a_failure_not_a_success():
    # The read-back is the whole reason download does not stop at "logged out
    # with no exception". A session that raises nothing and writes nothing is
    # what that check is for; it is caught by the controller's CRC not having
    # moved, which on a real controller it does on every download.
    device = Device(crc=CRC_B)
    ide_globals = ide(allowed=["download"], device=device)
    ide_globals["online"].session = Session(device=device, writes=[])
    outcome = silent.run(ide_globals, PLC_BODY, "download", {"yes": True})
    assert not outcome.ok()
    assert "nothing was written to it" in outcome.error_text()
    assert plc_crc_module.read_records(
        plc_crc_module.record_path(PROJECT_PATH)) == {}


def test_a_controller_that_lost_everything_during_a_download_is_a_failure():
    class Wiped(Device):
        def upload_file(self, remote, local, overwrite):
            self.crc = None if self.uploaded else self.crc
            Device.upload_file(self, remote, local, overwrite)

    ide_globals = ide(allowed=["download"], device=Wiped(crc=CRC_B))
    outcome = silent.run(ide_globals, PLC_BODY, "download", {"yes": True})
    assert not outcome.ok() and "nothing to show it landed" in \
        outcome.error_text()


def test_the_source_archive_comes_back_when_the_controller_has_one():
    ide_globals = ide(allowed=["connect"], device=Device(archive=True))
    data = silent.run(ide_globals, PLC_BODY, "connect", {}).result["data"]
    assert data["source_archive"].endswith(".projectarchive")


def test_no_source_archive_is_an_answer_not_a_failure():
    recorded(plc_crc="11223344")
    ide_globals = ide(allowed=["connect"], device=Device(archive=False))
    outcome = silent.run(ide_globals, PLC_BODY, "connect", {})
    assert outcome.result["data"]["source_archive"] is None
    assert outcome.ok()


def test_the_missing_archive_is_said_in_words_before_the_ides_own():
    # The IDE's words for it are "Value cannot be null. Parameter name: path",
    # which tells a reader nothing at all about what happened.
    ide_globals = ide(allowed=["connect"], device=Device(archive=False))
    outcome = silent.run(ide_globals, PLC_BODY, "connect", {})
    note = [n for n in outcome.result["data"]["notes"] if "archive" in n][0]
    assert note.startswith("no source archive to fetch: nothing has been "
                           "source-downloaded to this controller")


def test_the_files_the_controller_holds_are_named_not_counted():
    ide_globals = ide(allowed=["connect"])
    data = silent.run(ide_globals, PLC_BODY, "connect", {}).result["data"]
    assert any("Application.crc" in line for line in data["plc_files"])


def test_the_connection_is_closed_even_when_the_comparison_fails():
    device = Device(crc=None)
    ide_globals = ide(allowed=["connect"], device=device)
    silent.run(ide_globals, PLC_BODY, "connect", {})
    assert device.connected is False


def test_a_controller_that_does_not_answer_is_a_sentence_not_a_traceback():
    # A bench command that prints a traceback says "cdsint is broken" when
    # what happened is that the machine was switched off.
    class Unplugged(Device):
        def connect(self):
            raise RuntimeError("No connection to device. (Device unplugged?)")

    outcome = silent.run(ide(allowed=["connect"], device=Unplugged()),
                         PLC_BODY, "connect", {})
    said = outcome.error_text()
    assert "did not answer" in said and "Traceback" not in said


def test_a_download_that_throws_is_named_and_still_logs_out():
    class Refusing(Session):
        def login(self, option, delete_foreign_apps):
            Session.login(self, option, delete_foreign_apps)
            raise RuntimeError("the controller refused the login")

    ide_globals = ide(allowed=["download"])
    ide_globals["online"].session = Refusing()
    outcome = silent.run(ide_globals, PLC_BODY, "download", {"yes": True})
    said = outcome.error_text()
    assert "did not complete" in said and "Traceback" not in said
    # Leaving a session logged in would hold the controller for the next run.
    assert ("logout",) in ide_globals["online"].session.calls


def test_last_weeks_crc_is_not_read_as_this_weeks_answer(workspace):
    # The workspace is named after the project so runs overwrite each other,
    # which is exactly what makes a file nobody rewrote dangerous: an upload
    # that returns without writing would otherwise be answered from a file
    # the last run left there.
    class Silent(Device):
        def upload_file(self, remote, local, overwrite):
            self.uploaded.append(remote)   # as a controller might, and has

    stale = os.path.join(str(workspace), "cdsint", "plc", "Line")
    os.makedirs(stale)
    with open(os.path.join(stale, "plc_Application.crc"), "wb") as handle:
        handle.write(CRC_B)
    recorded(plc_crc="11223344")
    outcome = silent.run(ide(allowed=["connect"], device=Silent()),
                         PLC_BODY, "connect", {})
    assert crc_of(outcome) == "UNKNOWN"


# --------------------------------------------------------------------------
# Which device, and which gateway
# --------------------------------------------------------------------------

def test_a_project_with_no_device_says_so_rather_than_connecting():
    ide_globals = ide(allowed=["connect"], children=[Node("Application")])
    outcome = silent.run(ide_globals, PLC_BODY, "connect", {})
    assert not outcome.ok() and "no device node" in outcome.error_text()


def test_two_devices_are_named_and_nothing_is_picked():
    # Which controller to download to has no safe default and no flag to
    # answer it with, so the honest answer is to stop (SPEC D7).
    ide_globals = ide(allowed=["download"],
                      children=[Node("Left", DEVICE_GUID),
                                Node("Right", DEVICE_GUID)])
    outcome = silent.run(ide_globals, PLC_BODY, "download", {"yes": True})
    said = outcome.error_text()
    assert "Left" in said and "Right" in said
    assert ide_globals["online"].session.calls == []


def test_without_the_gateway_flag_the_projects_own_settings_are_left_alone():
    # A read-only command that rewrote the project's gateway on its way past
    # would be changing the project to answer a question about it.
    device_node = Node("Device", DEVICE_GUID)
    ide_globals = ide(allowed=["connect"], children=[device_node])
    silent.run(ide_globals, PLC_BODY, "connect", {})
    assert device_node.gateway_set_to is None


def test_the_gateway_flag_aims_the_device_and_says_where():
    gateway = Gateway()
    device_node = Node("Device", DEVICE_GUID)
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
                      children=[Node("Device", DEVICE_GUID)],
                      gateways=[Gateway()])
    with pytest.raises(Killed):
        silent.run(ide_globals, PLC_BODY, "connect",
                   {"gateway": "192.168.1.5", "port": 11740})
    assert "192.168.1.5" in capsys.readouterr().out


def test_a_gateway_with_no_port_uses_the_standard_device_port():
    gateway = Gateway()
    device_node = Node("Device", DEVICE_GUID)
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

def engine_module(name):
    """One engine module as an ordinary import, for the parts with no IDE."""
    import importlib
    return importlib.import_module("engine." + name)


def test_the_credential_dialog_is_switched_off_before_anything_connects():
    # Under --noUI a dialog nobody can answer is not a failure, it is a
    # process that never returns, so this is the line that makes the command
    # unattended at all.
    plc = engine_module("plc_link")
    online = Online()
    note, problem = plc.silence_credential_dialogs(
        online, {"CredentialSourceKind": CredentialSourceKind})
    assert problem is None
    assert online.auth_fallback_modes == "no-dialog"
    assert "auth_fallback_modes" in note


def test_an_ide_with_only_the_old_setter_is_switched_off_through_it():
    # 4.2.0.0 has the property and no method; 4.0.0.0 has not been looked at,
    # so the old spelling stays as a fallback instead of being deleted.
    plc = engine_module("plc_link")

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
    plc = engine_module("plc_link")
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
    plc = engine_module("plc_link")
    monkeypatch.setenv(plc.USER_ENV, "dev")
    monkeypatch.setenv(plc.PASS_ENV, "s3cret")
    online = Online()
    plc.silence_credential_dialogs(online, {"CredentialSourceKind":
                                            CredentialSourceKind})
    assert online.credentials == ("dev", "s3cret")


def test_no_environment_login_is_reported_rather_than_invented(monkeypatch):
    plc = engine_module("plc_link")
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
    plc = engine_module("plc_link")
    monkeypatch.setenv(plc.USER_ENV, "dev")
    monkeypatch.setenv(plc.PASS_ENV, "s3cret-do-not-print")
    ide_globals = ide(allowed=["download"])
    outcome = silent.run(ide_globals, PLC_BODY, "download", {"yes": True})
    written = repr(outcome.result) + outcome.stdout_tail + repr(
        outcome.messages)
    assert "s3cret-do-not-print" not in written
    assert "dev" in written


# --------------------------------------------------------------------------
# The pieces, on their own
# --------------------------------------------------------------------------

RECORD = {"plc_crc": "11223344", "downloaded_at": "2026-09-06T10:00:00"}


@pytest.mark.parametrize("record,plc,verdict", [
    (RECORD, "11223344", "MATCH"),
    (RECORD, "55667788", "DIFFERENT"),   # somebody loaded something else
    (None, "11223344", "UNKNOWN"),       # nothing was ever put on it from here
    (RECORD, None, "UNKNOWN"),           # nothing is on it at all
    (None, None, "UNKNOWN"),
])
def test_the_comparison_has_three_answers_not_two(record, plc, verdict):
    assert engine_module("plc_crc").judge(record, plc)[0] == verdict


def test_each_answer_says_what_it_is_about_rather_than_just_naming_itself():
    # UNKNOWN twice over is two different situations and two different next
    # steps, so the word on its own is not the answer.
    judge = engine_module("plc_crc").judge
    assert "loaded with something else since" in judge(RECORD, "55667788")[1]
    assert "download -y" in judge(None, "11223344")[1]
    assert "nothing on it" in judge(RECORD, None)[1]
    assert "2026-09-06T10:00:00" in judge(RECORD, "11223344")[1]


def test_a_second_controller_does_not_erase_the_first(tmp_path):
    # One working copy serving two benches is the bench itself: A and B are
    # the same project at two addresses. A download to the second that wiped
    # what was known about the first would make a later connect to the first
    # answer UNKNOWN about a controller cdsint did load.
    plc_crc = engine_module("plc_crc")
    path = str(tmp_path / "Line.cdsint-plc.json")
    plc_crc.remember(path, "127.0.0.1:11740", {"plc_crc": "AAAA"})
    plc_crc.remember(path, "127.0.0.1:11741", {"plc_crc": "BBBB"})
    records = plc_crc.read_records(path)
    assert records["127.0.0.1:11740"]["plc_crc"] == "AAAA"
    assert records["127.0.0.1:11741"]["plc_crc"] == "BBBB"


def test_a_record_nobody_can_read_is_no_record_rather_than_a_crash(tmp_path):
    # A bench command that dies on a corrupt side file is worse than one that
    # says it has nothing to compare against.
    plc_crc = engine_module("plc_crc")
    path = str(tmp_path / "Line.cdsint-plc.json")
    with open(path, "w") as handle:
        handle.write("{not json")
    assert plc_crc.read_records(path) == {}


def test_a_run_with_no_gateway_flag_is_filed_under_its_own_name():
    # "whatever the project already carried" is not an address, and filing it
    # under a guessed one would let two different controllers share a record.
    plc_crc = engine_module("plc_crc")
    assert plc_crc.controller_key(None, 11740) == plc_crc.PROJECT_GATEWAY
    assert plc_crc.controller_key("127.0.0.1", 11740) == "127.0.0.1:11740"


def test_a_project_that_was_never_saved_has_nowhere_to_keep_a_record():
    assert engine_module("plc_crc").record_path(None) is None
    assert engine_module("plc_crc").remember(None, "key", {}) is False


def test_a_file_too_short_to_hold_the_field_is_no_answer():
    # Truncated files would otherwise compare equal to each other.
    assert engine_module("plc_crc").crc_field(b"\x00\x01\x02") is None
    assert engine_module("plc_crc").crc_field(None) is None


def test_the_field_is_bytes_five_to_eight():
    assert engine_module("plc_crc").crc_field(CRC_A) == "DEADBEEF"
