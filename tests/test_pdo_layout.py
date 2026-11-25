# -*- coding: utf-8 -*-
"""Whether a slave's channels match its assigned PDOs (SPEC 6.10, GitHub #16)."""
from cds.core import pdo_layout as pl
from tests.device_fakes import OTHER_TX_PDO, RX_PDO, TX_PDO, pdo_values

CHANNELS = {"c1": {pl.INPUT: 48, pl.OUTPUT: 16}}


def doc(values, maps=()):
    return {"ident": "x", "values": values, "maps": dict(maps)}


def test_a_list_that_matches_has_no_problem():
    assert pl.problems(pdo_values(), CHANNELS) == []


def test_the_field_failure_is_named():
    # The PDO and the sync manager's length moved and the channels did not.
    values = pdo_values(other_sm="3", in_length="10")
    assert pl.problems(values, CHANNELS) == [
        "c1: the assigned PDOs are 80 input bits and the channels are 48"]


def test_each_direction_is_its_own_account():
    assert pl.channel_problems(pdo_values(), {"c1": {
        pl.INPUT: 48, pl.OUTPUT: 8}}) == [
        "c1: the assigned PDOs are 16 output bits and the channels are 8"]


def test_a_length_that_is_not_its_pdos_is_named():
    assert pl.length_problems(pdo_values(in_length="40")) == [
        "c1: the PDOs on sync manager 3 are 6 bytes and its length is 40"]


def test_lengths_are_whole_bytes_and_may_be_hexadecimal():
    values = pdo_values(in_length="16#07")
    values["c1/%d/Size" % (TX_PDO + 2)] = "17"
    assert pl.length_problems(values) == []


def test_a_sync_manager_that_is_not_there_is_named():
    assert pl.length_problems(pdo_values(other_sm="9")) == [
        "c1: there is no sync manager 9"]


def test_a_pdo_short_of_entries_is_named():
    values = pdo_values()
    del values["c1/%d/Size" % (TX_PDO + 2)]
    assert ("c1: PDO 16#1A00 says it has 2 entries and has 1"
            in pl.channel_problems(values, CHANNELS))


def test_a_drive_whose_module_has_the_channels_is_not_compared():
    assert pl.problems(pdo_values(), {"c1": {pl.INPUT: 0, pl.OUTPUT: 0}}) == []


def test_a_module_has_no_sync_manager_to_disagree_with():
    values = dict((k, v) for k, v in pdo_values().items()
                  if "/134217728" not in k)
    assert pl.length_problems(values) == []
    assert not pl.can_rebuild(values, CHANNELS, "c1")
    assert pl.can_rebuild(pdo_values(), CHANNELS, "c1")


def test_a_device_without_pdos_has_nothing_to_compare():
    assert pl.problems({"c1/35601": "1", "dev/7": "x"}, CHANNELS) == []


def test_moved_names_the_pdos_on_another_sync_manager():
    have, wanted = doc(pdo_values()), doc(pdo_values(other_sm="3"))
    assert pl.moved(have, wanted) == {"c1/%d/Sm" % OTHER_TX_PDO: "3"}
    assert pl.moved(have, doc({})) == {}


def test_resized_names_the_entry_sizes_a_file_changes():
    key = "c1/%d/Size" % (RX_PDO + 2)
    wanted = pdo_values()
    wanted[key] = "32"
    assert pl.resized(doc(pdo_values()), doc(wanted)) == [key]
    assert pl.resized(doc(pdo_values()), doc({})) == []


def test_merged_takes_the_files_value_only_where_the_device_has_the_key():
    have, wanted = doc({"c1/1": "a", "c1/2": "b"}), doc({"c1/1": "z", "c1/9": "z"})
    assert pl.merged(have, wanted) == {"c1/1": "z", "c1/2": "b"}


def test_a_mandatory_pdo_taken_off_is_named():
    have = pdo_values()
    have["c1/%d/Mandatory" % TX_PDO] = "True"
    wanted = dict(have)
    wanted["c1/%d/Sm" % TX_PDO] = "-1"
    assert pl.dropped_mandatory(doc(have), doc(wanted)) == [
        "c1/%d/Sm" % TX_PDO]
    assert pl.dropped_mandatory(doc(have), doc(have)) == []


def test_an_untouched_map_line_whose_variable_moved_has_the_old_number():
    have, rebuilt = doc({}, {"c1/20": "xA"}), doc({}, {"c1/20": "", "c1/18": "xA"})
    assert pl.old_numbering(have, rebuilt, doc({}, {"c1/20": "xA"})) == ["c1/20"]
    # Renumbered with the list, or mapped anew by hand: the file means it.
    assert pl.old_numbering(have, rebuilt, doc({}, {"c1/18": "xA"})) == []
    assert pl.old_numbering(have, rebuilt, doc({}, {"c1/20": "xB"})) == []


def test_a_variable_the_rebuild_left_in_place_has_the_right_number():
    same = doc({}, {"c1/20": "xA"})
    assert pl.old_numbering(same, same, same) == []
