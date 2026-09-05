# -*- coding: utf-8 -*-
"""A tray balloon that fails to clean itself up must not reach the IDE.

show_toast returns immediately and a WinForms timer takes the icon down
later (SPEC D5). By then there is no script left to catch anything: the Tick
handler runs on the IDE's own message loop, so an exception out of it is an
unhandled exception in the IDE's process, which is a thread-exception dialog
on top of whatever the person was doing.

engine/codesys_ui.py starts with `import clr`, so CI can only reach it with
a stand-in for the .NET side. That is what these fakes are -- everything
here is a fake .NET object, not a mock of the code under test.
"""
import sys
import types

import pytest


class FakeTimer(object):
    def __init__(self):
        self.Interval = None
        self.started = False
        self.stopped = False
        self.disposed = False
        self.Tick = self

    # `timer.Tick += handler` on a .NET event; here it just records it.
    def __iadd__(self, handler):
        self.handler = handler
        return self

    def Start(self):
        self.started = True

    def Stop(self):
        self.stopped = True

    def Dispose(self):
        self.disposed = True


class SulkingIcon(object):
    """A NotifyIcon whose Dispose throws, which .NET objects do."""

    Icon = None
    Visible = False

    def ShowBalloonTip(self, timeout, title, message, icon):
        pass

    def Dispose(self):
        raise ValueError("the icon was already gone")


class _Fake(type):
    """A .NET namespace: every name in it is a class, made on demand."""

    def __getattr__(cls, name):
        return _fake(name)


def _fake(name):
    return _Fake(str(name), (object,), {})


@pytest.fixture
def ui(monkeypatch):
    """engine.codesys_ui with a stand-in .NET underneath it.

    The module opens with `import clr` and builds its dialog classes on top
    of System.Windows.Forms at import time, so CI cannot reach show_toast
    without standing in for both.
    """
    clr = types.ModuleType("clr")
    clr.AddReference = lambda name: None
    monkeypatch.setitem(sys.modules, "clr", clr)
    for name in ("System", "System.Windows", "System.Windows.Forms",
                 "System.Drawing"):
        module = types.ModuleType(name)
        module.__getattr__ = _fake
        monkeypatch.setitem(sys.modules, name, module)

    had = sys.modules.pop("engine.codesys_ui", None)
    import importlib
    module = importlib.import_module("engine.codesys_ui")
    yield module
    sys.modules.pop("engine.codesys_ui", None)
    if had is not None:
        sys.modules["engine.codesys_ui"] = had


@pytest.fixture
def toast(ui, monkeypatch):
    """show_toast wired to a timer the test can tick, and an icon that sulks."""
    timer = FakeTimer()
    monkeypatch.setattr(ui, "NotifyIcon", SulkingIcon, raising=False)
    monkeypatch.setattr(ui, "Timer", lambda: timer, raising=False)
    monkeypatch.setattr(ui, "SystemIcons", _fake("SystemIcons"), raising=False)
    monkeypatch.setattr(ui, "ToolTipIcon", _fake("ToolTipIcon"), raising=False)
    monkeypatch.setattr(ui, "_TOASTS", [], raising=False)
    return timer


def test_a_toast_that_cannot_be_disposed_does_not_reach_the_message_loop(
        ui, toast, capsys):
    ui.show_toast("Saved", "MC_Main.diff")
    toast.handler()

    assert "the icon was already gone" in capsys.readouterr().out


def test_a_toast_that_cannot_be_disposed_still_lets_go_of_its_objects(
        ui, toast):
    # _TOASTS is what keeps the icon and the timer from being collected. An
    # entry left in it is a tray icon that never goes away.
    ui.show_toast("Saved", "MC_Main.diff")
    toast.handler()

    assert ui._TOASTS == []
    assert toast.stopped and toast.disposed
