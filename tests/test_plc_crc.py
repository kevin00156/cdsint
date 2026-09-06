# -*- coding: utf-8 -*-
"""engine/plc_crc.py on its own: the verdict, the bytes and the record.

No IDE and no trip — pure bytes, paths and JSON, which is the reason that
module was split out of the trip in the first place.
"""
import pytest

from engine import plc_crc as plc_crc_module
from tests.plc_fakes import CRC_A


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
    assert plc_crc_module.judge(record, plc)[0] == verdict


def test_each_answer_says_what_it_is_about_rather_than_just_naming_itself():
    # UNKNOWN twice over is two different situations and two different next
    # steps, so the word on its own is not the answer.
    judge = plc_crc_module.judge
    assert "loaded with something else since" in judge(RECORD, "55667788")[1]
    assert "download -y" in judge(None, "11223344")[1]
    assert "nothing on it" in judge(RECORD, None)[1]
    assert "2026-09-06T10:00:00" in judge(RECORD, "11223344")[1]


def test_a_second_controller_does_not_erase_the_first(tmp_path):
    # One working copy serving two benches is the bench itself: A and B are
    # the same project at two addresses. A download to the second that wiped
    # what was known about the first would make a later connect to the first
    # answer UNKNOWN about a controller cdsint did load.
    plc_crc = plc_crc_module
    path = str(tmp_path / "Line.cdsint-plc.json")
    plc_crc.remember(path, "127.0.0.1:11740", {"plc_crc": "AAAA"})
    plc_crc.remember(path, "127.0.0.1:11741", {"plc_crc": "BBBB"})
    records = plc_crc.read_records(path)
    assert records["127.0.0.1:11740"]["plc_crc"] == "AAAA"
    assert records["127.0.0.1:11741"]["plc_crc"] == "BBBB"


def test_a_record_nobody_can_read_is_no_record_rather_than_a_crash(tmp_path):
    # A bench command that dies on a corrupt side file is worse than one that
    # says it has nothing to compare against.
    plc_crc = plc_crc_module
    path = str(tmp_path / "Line.cdsint-plc.json")
    with open(path, "w") as handle:
        handle.write("{not json")
    assert plc_crc.read_records(path) == {}


def test_a_run_with_no_gateway_flag_is_filed_under_its_own_name():
    # "whatever the project already carried" is not an address, and filing it
    # under a guessed one would let two different controllers share a record.
    plc_crc = plc_crc_module
    assert plc_crc.controller_key(None, 11740) == plc_crc.PROJECT_GATEWAY
    assert plc_crc.controller_key("127.0.0.1", 11740) == "127.0.0.1:11740"


def test_a_project_that_was_never_saved_has_nowhere_to_keep_a_record():
    assert plc_crc_module.record_path(None) is None
    assert plc_crc_module.remember(None, "key", {}) is False


def test_a_file_too_short_to_hold_the_field_is_no_answer():
    # Truncated files would otherwise compare equal to each other.
    assert plc_crc_module.crc_field(b"\x00\x01\x02") is None
    assert plc_crc_module.crc_field(None) is None


def test_the_field_is_bytes_five_to_eight():
    assert plc_crc_module.crc_field(CRC_A) == "DEADBEEF"
