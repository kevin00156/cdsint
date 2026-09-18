# -*- coding: utf-8 -*-
"""The cache doctor answers with the engine's own predicate, not a copy of it.

It used to replay two hand-written expressions, one per side, because that
was the bug it was built to find: export compared int(st_mtime) and compare
compared a float, so each side rejected everything the other had written.
That is fixed -- both sides go through sync_cache.file_signature() -- and
a diagnostic still replaying the old expressions reports a war that is over
and misjudges a healthy cache.

So it imports file_signature() now. These tests are what stops it drifting
again: they build the cache with the engine's own writer and then ask the
doctor what it sees.
"""
import io
import os

import pytest

from engine.sync_cache import CACHE_VERSION
from engine.sync_cache import file_signature, save_sync_cache
from tools import cache_doctor


@pytest.fixture
def synced(tmp_path):
    """A sync folder with one .st file and a cache that matches it."""
    st = tmp_path / "MC_Main.st"
    st.write_text(u"FUNCTION_BLOCK MC_Main\nEND_FUNCTION_BLOCK\n",
                  encoding="utf-8")
    mtime, size = file_signature(str(st))
    save_sync_cache(str(tmp_path),
                    {"MC_Main.st": {"ide_hash": "DEADBEEF",
                                    "disk_mtime": mtime, "disk_size": size}})
    return tmp_path, st


def report(base_dir, capsys):
    assert cache_doctor.main([str(base_dir)]) == 0
    return capsys.readouterr().out


def test_a_cache_the_engine_just_wrote_reads_as_a_hit(synced, capsys):
    # The whole point: what the engine writes, the doctor must accept. A
    # doctor that calls a healthy cache degraded sends people hunting for a
    # problem that is in the doctor.
    base_dir, _st = synced
    out = report(base_dir, capsys)
    assert "would skip       1" in out
    assert "DEGRADED" not in out


def test_an_edited_file_reads_as_work_and_is_named(synced, capsys):
    base_dir, st = synced
    st.write_text(u"FUNCTION_BLOCK MC_Main\nx := 1;\nEND_FUNCTION_BLOCK\n",
                  encoding="utf-8")

    out = report(base_dir, capsys)

    assert "would skip       0" in out
    assert "MC_Main.st" in out


def test_a_cache_the_engine_would_throw_away_is_the_first_thing_it_says(
        synced, capsys):
    # load_sync_cache() discards the whole file when the version or the type
    # profile has moved on, so every other number below would be about a
    # cache nobody is going to read.
    base_dir, _st = synced
    path = base_dir / "sync_cache.json"
    path.write_text(path.read_text(encoding="utf-8").replace(
        '"version":"%s"' % CACHE_VERSION, '"version":"3.0"'),
        encoding="utf-8")

    out = report(base_dir, capsys)

    assert "3.0" in out and CACHE_VERSION in out
    assert "rebuild" in out.lower()


def test_a_cache_from_another_type_profile_is_called_out_too(synced, capsys):
    base_dir, _st = synced
    path = base_dir / "sync_cache.json"
    text = path.read_text(encoding="utf-8")
    start = text.index('"profile_hash":"') + len('"profile_hash":"')
    end = text.index('"', start)
    path.write_text(text[:start] + "NOTTHEONE" + text[end:], encoding="utf-8")

    out = report(base_dir, capsys)

    assert "NOTTHEONE" in out
    assert "rebuild" in out.lower()
