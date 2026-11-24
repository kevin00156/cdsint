# -*- coding: utf-8 -*-
"""Tests for engine.sync_write -- a sync-folder file is the old one or the
new one, never half of one (CDSI-14)."""
import io
import os
import sys
import types

import pytest

from engine import sync_dir, sync_write


def _read(path):
    with io.open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def _write(path, text):
    with io.open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def test_a_new_file_gets_the_text(tmp_path):
    path = str(tmp_path / "PLC_PRG.st")
    sync_write.write_text(path, u"PROGRAM PLC_PRG\r\nEND_PROGRAM\r\n")
    assert _read(path) == u"PROGRAM PLC_PRG\r\nEND_PROGRAM\r\n"
    assert os.listdir(str(tmp_path)) == ["PLC_PRG.st"]


def test_an_existing_file_is_replaced(tmp_path):
    path = str(tmp_path / "PLC_PRG.st")
    _write(path, u"old")
    sync_write.write_text(path, u"// 中文\nnew\n")
    assert _read(path) == u"// 中文\nnew\n"
    assert os.listdir(str(tmp_path)) == ["PLC_PRG.st"]


class _Died(BaseException):
    """The IDE killed mid-write: no except clause gets to run."""


def test_a_death_mid_write_leaves_the_old_file_whole(tmp_path, monkeypatch):
    path = str(tmp_path / "PLC_PRG.st")
    _write(path, u"PROGRAM PLC_PRG\nEND_PROGRAM\n")
    real_open = io.open

    class _HalfHandle(object):
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.handle.close()

        def write(self, text):
            self.handle.write(text[:len(text) // 2])
            raise _Died()

    monkeypatch.setattr(sync_write.io, "open",
                        lambda *a, **k: _HalfHandle(real_open(*a, **k)))
    with pytest.raises(_Died):
        sync_write.write_text(path, u"PROGRAM PLC_PRG\nx := 1;\nEND_PROGRAM\n")
    monkeypatch.undo()
    assert _read(path) == u"PROGRAM PLC_PRG\nEND_PROGRAM\n"
    assert os.listdir(str(tmp_path)) == ["PLC_PRG.st"]


def test_a_failed_replace_keeps_the_old_file_and_drops_the_temp(
        tmp_path, monkeypatch):
    path = str(tmp_path / "PLC_PRG.st")
    _write(path, u"old")

    def locked(src, dst):
        raise OSError(13, "held by a scanner")
    monkeypatch.setattr(os, "replace", locked)
    with pytest.raises(OSError):
        sync_write.write_text(path, u"new")
    assert _read(path) == u"old"
    assert os.listdir(str(tmp_path)) == ["PLC_PRG.st"]


def test_a_temp_left_by_a_killed_run_does_not_break_the_next(tmp_path):
    path = str(tmp_path / "PLC_PRG.st")
    _write(path + sync_write.TMP, u"half of somethi")
    sync_write.write_text(path, u"whole")
    assert _read(path) == u"whole"
    assert os.listdir(str(tmp_path)) == ["PLC_PRG.st"]


def test_the_temp_is_not_a_sync_file(tmp_path):
    _write(str(tmp_path / ("PLC_PRG.st" + sync_write.TMP)), u"half")
    _write(str(tmp_path / ("Lib.libraries" + sync_write.TMP)), u"half")
    assert list(sync_dir.sync_files(str(tmp_path))) == []


# --- the branch only IronPython 2.7 takes ----------------------------------

class _FakeFile(object):
    """System.IO.File as the IDE has it: Move refuses an existing target."""
    calls = []

    @classmethod
    def Exists(cls, path):
        return os.path.exists(path)

    @classmethod
    def Replace(cls, src, dst, backup):
        assert backup is None
        cls.calls.append("Replace")
        os.remove(dst)
        os.rename(src, dst)

    @classmethod
    def Move(cls, src, dst):
        assert not os.path.exists(dst)
        cls.calls.append("Move")
        os.rename(src, dst)

    @classmethod
    def Delete(cls, path):
        cls.calls.append("Delete")
        os.remove(path)


@pytest.fixture
def ironpython(monkeypatch):
    monkeypatch.delattr(os, "replace", raising=False)
    system = types.ModuleType("System")
    system_io = types.ModuleType("System.IO")
    system_io.File = _FakeFile
    system.IO = system_io
    monkeypatch.setitem(sys.modules, "System", system)
    monkeypatch.setitem(sys.modules, "System.IO", system_io)
    _FakeFile.calls = []
    return _FakeFile


def test_without_os_replace_dotnet_moves_a_new_file_in(tmp_path, ironpython):
    path = str(tmp_path / "PLC_PRG.st")
    sync_write.write_text(path, u"new")
    assert _read(path) == u"new"
    assert ironpython.calls == ["Move"]
    assert os.listdir(str(tmp_path)) == ["PLC_PRG.st"]


def test_without_os_replace_dotnet_replaces_an_existing_file(
        tmp_path, ironpython):
    path = str(tmp_path / "PLC_PRG.st")
    _write(path, u"old")
    sync_write.write_text(path, u"new")
    assert _read(path) == u"new"
    assert ironpython.calls == ["Replace"]
    assert os.listdir(str(tmp_path)) == ["PLC_PRG.st"]


def test_a_volume_that_refuses_replace_still_gets_the_file(
        tmp_path, ironpython, monkeypatch):
    # ReplaceFile is refused on some network shares; the export must still
    # land there, one step or not.
    def refused(src, dst, backup):
        raise IOError("The request is not supported")
    monkeypatch.setattr(_FakeFile, "Replace", staticmethod(refused))
    path = str(tmp_path / "PLC_PRG.st")
    _write(path, u"old")
    sync_write.write_text(path, u"new")
    assert _read(path) == u"new"
    assert ironpython.calls == ["Delete", "Move"]
    assert os.listdir(str(tmp_path)) == ["PLC_PRG.st"]
