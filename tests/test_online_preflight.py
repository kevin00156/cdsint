# -*- coding: utf-8 -*-
"""Pre-flight for the "logged into a device" import failure.

CODESYS refuses to create, move or delete any object belonging to an
application that is logged into a PLC. Before this check an import hit that
refusal once per object ("Cannot add an object because it affects a device you
are currently logged into"), deep in the run, after the compare and the safety
backup — never naming the one fix: log out.

find_logged_in_applications must therefore see EVERY application (aliased type
GUIDs, several devices, apps under 'PLC Logic'), stay cheap on big projects,
and — crucially — report nothing rather than guess when the online API cannot
answer, so a blind pre-flight never blocks a legitimate import.
"""
import sys

import pytest

from tests.fakes import Node as BaseNode

from engine import codesys_online, object_paths


@pytest.fixture(scope="module")
def env():
    constants = sys.modules["engine.codesys_constants"]
    module = codesys_online
    return module, constants.TYPE_GUIDS, constants.KIND_GUIDS


@pytest.fixture(autouse=True)
def clean_caches():
    """The container-prefix cache is keyed by object GUID and lives in the
    module, so a device named PLC in one test answers for a device named PLC
    in the next. Real objects have unique GUIDs; these fakes derive theirs
    from the name, which is exactly the collision the cache is built to
    exploit. Same fixture as tests/test_path_cache.py.
    """
    object_paths.clear_path_caches()
    yield
    object_paths.clear_path_caches()


class WalkCountingNode(BaseNode):
    """The plain node, counting how often the tree was walked from it.

    online preflight is the one caller that must not walk twice
    (PRINCIPLES 3), so the count is the assertion, not a diagnostic.
    """

    def __init__(self, name, type_guid, children=None):
        BaseNode.__init__(self, name, type_guid, children=children)
        self.get_children_calls = 0

    def get_children(self, recursive=False):
        self.get_children_calls += 1
        return BaseNode.get_children(self, recursive)


class LoginSession(object):
    """ScriptOnlineApplication, as far as "is this one logged in" goes.

    Not plc_fakes.Session, which stands in for the same .NET class but for
    the download: login, create_boot_application, start, logout. The two
    share no method at all, so one fake for both would be a fake with two
    personalities and every test carrying the half it did not ask for.
    """

    def __init__(self, is_logged_in):
        self.is_logged_in = is_logged_in
        self.disposed = False

    def Dispose(self):
        self.disposed = True


class LoginStates(object):
    """The CODESYS `online` global, answering only which applications are
    logged in. plc_fakes.Online is the same global seen from the credentials
    and device-connection side; see LoginSession above."""

    def __init__(self, logged_in=(), unanswerable=()):
        self.logged_in = set(logged_in)
        self.unanswerable = set(unanswerable)
        self.sessions = []

    def create_online_application(self, application):
        name = application.get_name()
        if name in self.unanswerable:
            raise RuntimeError("No gateway configured")
        session = LoginSession(name in self.logged_in)
        self.sessions.append(session)
        return session


def _project(children):
    return WalkCountingNode("Project", "project-type", children)


def _device(name, guids, app_name="Application", under_plc_logic=False,
            app_guid=None):
    app = WalkCountingNode(app_name, app_guid or guids["application"])
    if under_plc_logic:
        return WalkCountingNode(name, guids["device"],
                    [WalkCountingNode("Plc Logic", guids["plc_logic"], [app])])
    return WalkCountingNode(name, guids["device"], [app])


def _find(module, project, online):
    """The online API is handed in now, not hunted for: the caller has the
    namespace the IDE injected it into (engine/entry.py's borrowed())."""
    return module.find_logged_in_applications(project, online)


# ── detection ──

def test_nothing_logged_in_reports_nothing(env):
    module, guids, _ = env
    project = _project([_device("PLC", guids)])
    assert _find(module, project, LoginStates()) == []


def test_logged_in_application_is_reported_with_device_prefix(env):
    module, guids, _ = env
    project = _project([_device("CODESYS_Control_for_Linux_SL", guids)])
    online = LoginStates(logged_in=["Application"])
    assert _find(module, project, online) == \
        ["CODESYS_Control_for_Linux_SL/Application"]


def test_application_under_plc_logic_is_found(env):
    module, guids, _ = env
    project = _project([_device("PLC", guids, under_plc_logic=True)])
    online = LoginStates(logged_in=["Application"])
    assert _find(module, project, online) == ["PLC/Application"]


def test_only_the_logged_in_device_is_reported(env):
    module, guids, _ = env
    project = _project([
        _device("PLC_A", guids, app_name="App1"),
        _device("PLC_B", guids, app_name="App2"),
    ])
    online = LoginStates(logged_in=["App2"])
    assert _find(module, project, online) == ["PLC_B/App2"]


def test_every_logged_in_application_is_reported(env):
    module, guids, _ = env
    project = _project([
        _device("PLC_A", guids, app_name="App1"),
        _device("PLC_B", guids, app_name="App2"),
    ])
    online = LoginStates(logged_in=["App1", "App2"])
    assert _find(module, project, online) == ["PLC_A/App1", "PLC_B/App2"]


def test_alias_application_guid_is_detected(env):
    module, guids, kind_guids = env
    alias = kind_guids["application"][-1]
    assert alias != guids["application"], "profile lost the application alias"
    project = _project([_device("PLC", guids, app_guid=alias)])
    online = LoginStates(logged_in=["Application"])
    # The alias is not the primary GUID, so get_container_prefix cannot see the
    # application — the label still has to name it.
    assert _find(module, project, online) == ["PLC/Application"]


def test_device_inside_a_folder_is_found(env):
    module, guids, _ = env
    project = _project([WalkCountingNode("Line1", guids["folder"],
                             [_device("PLC", guids)])])
    online = LoginStates(logged_in=["Application"])
    assert _find(module, project, online) == ["PLC/Application"]


# ── blind pre-flight must not block ──

def test_no_online_global_reports_nothing(env):
    module, guids, _ = env
    project = _project([_device("PLC", guids)])
    assert module.find_logged_in_applications(project, None) == []


def test_unanswerable_online_api_reports_nothing(env):
    module, guids, _ = env
    project = _project([_device("PLC", guids)])
    online = LoginStates(logged_in=["Application"], unanswerable=["Application"])
    assert _find(module, project, online) == []


def test_unlistable_container_does_not_crash_the_walk(env):
    module, guids, _ = env

    class Deaf(WalkCountingNode):
        def get_children(self, recursive=False):
            raise RuntimeError("object is being edited")

    project = _project([
        Deaf("Broken", guids["device"]),
        _device("PLC", guids),
    ])
    online = LoginStates(logged_in=["Application"])
    assert _find(module, project, online) == ["PLC/Application"]


# ── cost and hygiene ──

def test_every_session_is_disposed(env):
    module, guids, _ = env
    project = _project([
        _device("PLC_A", guids, app_name="App1"),
        _device("PLC_B", guids, app_name="App2"),
    ])
    online = LoginStates(logged_in=["App1"])
    _find(module, project, online)
    assert len(online.sessions) == 2
    assert all(session.disposed for session in online.sessions)


def test_walk_stops_at_the_application(env):
    module, guids, _ = env
    pou = WalkCountingNode("MainProgram", guids["pou"])
    app = WalkCountingNode("Application", guids["application"], [pou])
    project = _project([WalkCountingNode("PLC", guids["device"], [app])])
    _find(module, project, LoginStates())
    # Nothing below an application can be an application.
    assert app.get_children_calls == 0
    assert pou.get_children_calls == 0


def test_pou_pool_is_not_swept(env):
    module, guids, _ = env
    pous = [WalkCountingNode("POU%d" % i, guids["pou"]) for i in range(5)]
    pool = WalkCountingNode("Pool", guids["folder"], pous)
    project = _project([pool, _device("PLC", guids)])
    _find(module, project, LoginStates())
    assert pool.get_children_calls == 1          # folders may hold devices
    assert all(p.get_children_calls == 0 for p in pous)


# ── message ──

def test_block_message_names_the_applications_and_the_fix(env):
    module, _, _ = env
    message = module.logged_in_block_message(["PLC/App1", "PLC2/App2"])
    assert "PLC/App1" in message and "PLC2/App2" in message
    assert "Logout" in message
