# -*- coding: utf-8 -*-
"""The IDE the plc tests run against, and the fixtures that hold it up.

One copy, because the test_plc_*.py files each need most of it, and a
second copy of a fake controller is a second controller that can disagree
with the first.

Not a conftest.py: these fixtures put a stand-in engine.codesys_ui into
sys.modules and redirect tempfile, which is right for the plc tests and
wrong for every other test in the directory. A test module imports the
autouse fixtures it wants by name, and pytest collects a fixture from
wherever the module can see it.
"""
import os
import sys
import types

import pytest

from cds.core import settings
from cds.ide import entries
from engine import plc_crc as plc_crc_module
from tests.fakes import FakeSystem, Node as BaseNode, Project, Projects

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

class DeviceNode(BaseNode):
    """A device node: it remembers where its gateway was pointed."""

    def __init__(self, name, type_guid="not-a-device"):
        BaseNode.__init__(self, name, type_guid)
        self.gateway_set_to = None

    def set_gateway_and_ip_address(self, gateway, address, port):
        self.gateway_set_to = (gateway, address, port)


class Application(object):
    """The project's active application: what a download is a download of.

    It has no create_boot_application of its own any more. The offline call
    that writes one to a path was how the verdict used to be reached, and
    engine/plc_crc.py records why that could not work; a fake that still
    offered it would keep the idea alive in the one place nobody would look.
    """


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
    children = children if children is not None else [DeviceNode("Device",
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
