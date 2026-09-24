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
import io
import os
import sys
import types

import pytest

from cds.core import settings
from cds.core import trace_run
from cds.ide import entries
from engine import plc_crc as plc_crc_module
from engine.codesys_constants import TYPE_GUIDS
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

# The controller's Application.app header, measured on the bench, and the
# .bootinfo_guids the IDE wrote beside the project on that download: the two
# agree, which is what a trace needs before it logs in (SPEC 6.8 step 2).
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def read_binary(name):
    with open(os.path.join(DATA, name), "rb") as handle:
        return handle.read()


APP_HEADER = read_binary("plc_app_header_bench.bin")
APP_HEADER_OLD = read_binary("plc_app_header_old.bin")
BOOTINFO_GUIDS = read_binary("plc_bootinfo_guids.bin")
BOOTINFO_GUID = "bf63ef63-1caa-4ad4-b499-847051c1c69f"

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

    def __init__(self, crc=CRC_B, archive=True, app=APP_HEADER):
        self.crc = crc
        self.app = app
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
        held = self.app if remote.endswith(".app") else self.crc
        if held is None:
            raise IOError("Could not find a part of the path: " + remote)
        with open(local, "wb") as handle:
            handle.write(held)

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
    Keep = "keep"


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fake_codesys_ui():
    """The dialog module, which needs clr and so cannot be the real one.

    cds/ide/silent.py swaps its two dialog functions for stand-ins that
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


def ide(allowed=("connect", "download", "trace"), device=None, application=None,
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


def download_info(guids=BOOTINFO_GUIDS, compileinfo=True, guid=BOOTINFO_GUID,
                  device="Device", application="Application"):
    """Write the files the IDE leaves beside the project on a download.

    Hands back the .bootinfo_guids path. `guids=None` writes none.
    """
    stem = os.path.splitext(PROJECT_PATH)[0]
    prefix = "%s.%s.%s.%s" % (stem, device, application, guid)
    if guids is not None:
        with open(prefix + ".bootinfo_guids", "wb") as handle:
            handle.write(guids)
    if compileinfo:
        with open(prefix + ".compileinfo", "wb") as handle:
            handle.write(b"compile info")
    return prefix + ".bootinfo_guids"


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
# The trace plug-in, the online application it records through, and a clock
# that moves only when the run holds (SPEC 6.8). One bench object ties them
# together, because the order of calls across all of them is what the tests
# check: the prompt answer set, the download, the answer removed, the start.
# --------------------------------------------------------------------------

TASK_CONFIG_XML = os.path.join(DATA, "trace_task_config.xml")
SAMPLE_CSV = os.path.join(DATA, "trace_sample.csv")

# The two variables in the sample CSV, and what read_value says about each.
TRACED = ["PRG_AxisControl._uFlags", "PRG_AxisControl._iOvrZone"]
VALUES = {"PRG_AxisControl._uFlags": "UDINT#0",
          "PRG_AxisControl._iOvrZone": "INT#3"}

# The task in the fixture whose 1000 us period the sample CSV was recorded at.
TASK = "EtherCAT_Task"
GATEWAY = "127.0.0.1"
PORT = 11741


def read_data(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def gapped_csv():
    """The sample CSV with ten of the first variable's samples gone."""
    lines = read_data(SAMPLE_CSV).splitlines(True)
    first = [i for i, line in enumerate(lines) if line.startswith(u";")][:20]
    dropped = set(first[5:15])
    return u"".join(line for i, line in enumerate(lines) if i not in dropped)


class Answers(dict):
    """system.prompt_answers, remembering when a key came and went."""

    def __init__(self, log):
        dict.__init__(self)
        self.log = log

    def __setitem__(self, key, value):
        self.log.append(("answer set", key, value))
        dict.__setitem__(self, key, value)

    def __delitem__(self, key):
        self.log.append(("answer removed", key))
        dict.__delitem__(self, key)


class TraceSystem(FakeSystem):
    def __init__(self, log):
        FakeSystem.__init__(self)
        self.prompt_answers = Answers(log)


# What the editor says on each packet-state poll after start(), as
# (packet state, trigger state); the last pair repeats. Research 13.4 saw a
# trigger go WaitForTrigger, TriggerReached, then stop by itself.
UNTRIGGERED = [("Started", "Disabled")]
TRIGGER_FIRES = [("Started", "WaitForTrigger"), ("Started", "TriggerReached"),
                 ("Stopped", "TriggerReached")]
TRIGGER_NEVER = [("Started", "WaitForTrigger")]
TRIGGER_UNFINISHED = [("Started", "WaitForTrigger"),
                      ("Started", "TriggerReached")]


class TraceEditor(object):
    """The trace editor: download, start, stop, save, and its two states.

    After start() each get_packet_state() moves one step along the script,
    so a trace with a trigger stops by itself as the real one did. stop()
    refuses a trace that is not Started, in the IDE's words (research 13.4).
    save() writes what the IDE would write for the extension: the CSV the
    bench recorded for `.csv`, a marker for anything else.
    """

    def __init__(self, log, csv_text, api, trigger_script):
        self.log = log
        self.csv_text = csv_text
        self.api = api
        self.trigger_script = trigger_script
        self.script = [("Stopped", "Disabled")]
        self.polls = 0

    def download(self):
        self.log.append(("download",))

    def start(self):
        self.log.append(("start",))
        self.script = (self.trigger_script if self.api.trigger_enabled
                       else UNTRIGGERED)
        self.polls = 0

    def _now(self):
        return self.script[min(self.polls, len(self.script) - 1)]

    def get_packet_state(self):
        state = self._now()[0]
        self.polls += 1
        return state

    def get_trigger_state(self):
        return self._now()[1]

    def stop(self):
        self.log.append(("stop",))
        if self._now()[0] != "Started":
            raise RuntimeError("Cannot stop the trace in the current state")
        self.script = [("Stopped", self._now()[1])]

    def save(self, path):
        self.log.append(("save", path))
        text = self.csv_text if path.endswith(".csv") else u"not a csv"
        with io.open(path, "w", encoding="utf-8") as handle:
            handle.write(text)


class TriggerEdge(object):
    """The plug-in's edge enum: reached only through type(api.trigger_edge)."""

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return "TriggerEdge.%s" % self.name


for _edge in ("Positive", "Negative", "Both"):
    setattr(TriggerEdge, _edge, TriggerEdge(_edge))


class TraceApi(object):
    """What trace.create() hands back: the settings of one trace object.

    `assigned` is every trigger and condition setting in the order it was
    made, because a half-set trigger breaks the next start() (research 4).
    """

    def __init__(self, log, csv_text, trigger_script):
        self.log = log
        self.variables = []
        self.resolution = None
        self.every_n_cycles = None
        self.trigger_variable = None
        self.trigger_edge = TriggerEdge.Positive
        self.trigger_level = None
        self.post_trigger_samples = None
        self.trigger_enabled = False
        self.record_condition = None
        self.assigned = []      # from here on, every setting is recorded
        self.editor = TraceEditor(log, csv_text, self, trigger_script)

    def __setattr__(self, name, value):
        if hasattr(self, "assigned") and (name.startswith("trigger_") or name
                                          in ("post_trigger_samples",
                                              "record_condition")):
            self.assigned.append((name, value))
        object.__setattr__(self, name, value)

    def add_trace_variable(self, variableName):
        self.variables.append(variableName)

    def open_editor(self):
        self.log.append(("open_editor",))
        return self.editor


class Tracer(object):
    """The IDE's `trace` global."""

    def __init__(self, log, csv_text, trigger_script):
        self.log = log
        self.api = TraceApi(log, csv_text, trigger_script)
        self.created = []

    def create(self, application, name, task):
        self.log.append(("create", name, task))
        self.created.append((application, name, task))
        return self.api


class TraceSession(Session):
    """The online application a trace logs in through.

    read_value answers from `values` and says "Invalid expression" for any
    other name, as the controller does; `refuse_login` is the IDE's words for
    a login that did not happen.
    """

    def __init__(self, log, values=None, state="run", refuse_login=None):
        Session.__init__(self)
        self.log = log
        self.values = dict(VALUES if values is None else values)
        self.application_state = state
        self.refuse_login = refuse_login

    def login(self, option, delete_foreign_apps):
        self.log.append(("login", option, delete_foreign_apps))
        if self.refuse_login:
            raise RuntimeError(self.refuse_login)

    def read_value(self, name):
        self.log.append(("read_value", name))
        if name not in self.values:
            raise RuntimeError("Invalid expression")
        return self.values[name]

    def logout(self):
        self.log.append(("logout",))


class Resolution(object):
    MicroSeconds = "microseconds"
    MilliSeconds = "milliseconds"


class PromptResult(object):
    OK = "ok"


class TraceProject(Project):
    """The open project: it can find by name and export native XML."""

    def __init__(self, children, application, xml, names=()):
        Project.__init__(self, {}, children, PROJECT_PATH, application)
        self.xml = xml
        self.names = list(names)

    def find(self, name, recursive=False):
        return [n for n in self.names if n.lower() == name.lower()]

    def export_native(self, objects, path, recursive=False):
        self.exported = (objects, recursive)
        with io.open(path, "w", encoding="utf-8") as handle:
            handle.write(self.xml)


class FakeClock(object):
    """Wall time that moves only when the run holds."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class Buffers(object):
    """The private-member seam: records what it was asked to set."""

    def __init__(self, present=True):
        self.present = present
        self.set_to = None

    def __call__(self, api):
        if not self.present:
            return None

        def set_buffers(ring, per_variable):
            self.set_to = (ring, per_variable)
        return set_buffers


def trace_job(**overrides):
    """A job as the CLI hands it over: normalised, with `out` absolute."""
    job = {"task": TASK, "variables": list(TRACED), "duration_s": 1.0,
           "out": os.path.join(os.path.dirname(PROJECT_PATH), "out", "run")}
    job.update(overrides)
    return job


class TraceBench(object):
    """One IDE, one controller, one clock: everything a trace run touches."""

    def __init__(self, csv_text=None, xml=None, names=(), crc=CRC_B,
                 record="11223344", app=APP_HEADER, guids=BOOTINFO_GUIDS,
                 trigger_script=TRIGGER_FIRES, settings_file=None, **session):
        self.log = []
        self.clock = FakeClock()
        self.buffers = Buffers()
        self.settings_file = settings_file or {}
        self.tracer = Tracer(self.log, read_data(SAMPLE_CSV)
                             if csv_text is None else csv_text,
                             trigger_script)
        self.task_config = BaseNode("Task configuration",
                                    TYPE_GUIDS["task_config"])
        self.application = BaseNode("Application", "an-application",
                                    [self.task_config])
        self.project = TraceProject(
            [DeviceNode("Device", DEVICE_GUID)], self.application,
            read_data(TASK_CONFIG_XML) if xml is None else xml, names)
        self.online = Online(device=Device(crc=crc, app=app),
                             gateways=[Gateway()])
        self.online.session = TraceSession(self.log, **session)
        if record:
            recorded(plc_crc=record, controller="%s:%d" % (GATEWAY, PORT))
        if guids is not None:
            download_info(guids)

    def hold_ms(self, milliseconds):
        self.log.append(("hold", milliseconds))
        self.clock.now += milliseconds / 1000.0

    def globals(self, ui=False):
        """The IDE globals, with the settings file allowing trace."""
        written = {"plc": ["trace"]}
        written.update(self.settings_file)
        settings.write(settings.path_for(PROJECT_PATH), written)
        return {"system": TraceSystem(self.log),
                "projects": Projects(self.project), "online": self.online,
                "trace": self.tracer, "Resolution": Resolution,
                "PromptResult": PromptResult,
                "CredentialSourceKind": CredentialSourceKind,
                "OnlineChangeOption": OnlineChangeOption,
                trace_run.HOLD_GLOBAL: None if ui else self.hold_ms}

    def args(self, job=None, gateway=GATEWAY):
        return {"gateway": gateway, "port": PORT,
                "job": trace_job() if job is None else job}

    def run(self, job=None, gateway=GATEWAY, ui=False):
        """The trace body on this bench, with its clock and its buffers."""
        from engine import entry_plc
        from engine.plc_trace import TraceTrip
        trip = TraceTrip(self.args(job, gateway), self.globals(ui),
                         clock=self.clock, buffers_for=self.buffers)
        return entry_plc.traced(trip)

    def calls(self, *kinds):
        return [call for call in self.log if call[0] in kinds]
