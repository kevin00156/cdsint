# -*- coding: utf-8 -*-
"""The download identities: the controller's .app header against the IDE's files.

The three fixtures are real bytes: the bench controller's Application.app
header, an older local build's, and the .bootinfo_guids the IDE wrote on the
bench download. Everything else is those bytes bent one way at a time, to
pin that a layout cdsint has not measured is refused, never guessed at.
"""
import os

from engine import plc_identity
from tests.plc_fakes import (APP_HEADER, APP_HEADER_OLD, BOOTINFO_GUID,
                             BOOTINFO_GUIDS)

DEVICE = "CODESYS_Control_for_Linux_SL"
APPLICATION = "Application"


def project_in(tmp_path, name="softplc_refactor.project"):
    return os.path.join(str(tmp_path), name)


def write_info(project, guids=BOOTINFO_GUIDS, guid=BOOTINFO_GUID,
               compileinfo=True, device=DEVICE, application=APPLICATION):
    prefix = "%s.%s.%s.%s" % (os.path.splitext(project)[0], device,
                              application, guid)
    with open(prefix + ".bootinfo_guids", "wb") as handle:
        handle.write(guids)
    if compileinfo:
        with open(prefix + ".compileinfo", "wb") as handle:
            handle.write(b"x")
    return prefix + ".bootinfo_guids"


def header_named(name, identity=BOOTINFO_GUIDS, tag=b"\x71\xa0\x80\x00"):
    """An .app header in the measured layout, for an application `name`."""
    head = APP_HEADER[:plc_identity.NAME_AT] + name + b"\x00"
    head += b"\x00" * (-len(head) % 4)
    return head + tag + identity + b"\x74\x84\x80\x00"


# -- the controller's header ------------------------------------------------

def test_the_bench_header_carries_the_bench_download_info():
    assert plc_identity.app_identity(APP_HEADER) == (BOOTINFO_GUIDS, None)


def test_an_older_build_carries_other_identities():
    identity, problem = plc_identity.app_identity(APP_HEADER_OLD)
    assert problem is None and len(identity) == 32
    assert identity != BOOTINFO_GUIDS


def test_a_name_of_another_length_is_padded_to_four():
    for name in (b"App", b"Appl", b"MyApplication_2"):
        identity, problem = plc_identity.app_identity(header_named(name))
        assert (identity, problem) == (BOOTINFO_GUIDS, None), name


def test_the_measured_layout_is_the_one_the_synthetic_header_builds():
    assert header_named(b"Application") == APP_HEADER[:0x3C]


def test_a_wrong_tag_is_a_layout_cdsint_does_not_recognise():
    identity, problem = plc_identity.app_identity(
        header_named(b"Application", tag=b"\x72\xa0\x80\x00"))
    assert identity is None
    assert "does not recognise" in problem and "72A08000" in problem
    assert "plc download -y" in problem


def test_a_short_header_is_refused():
    identity, problem = plc_identity.app_identity(APP_HEADER[:0x30])
    assert identity is None and "does not recognise" in problem


def test_no_name_or_no_file_is_refused():
    for raw in (None, b"", APP_HEADER[:8] + b"\x00" * 8, b"x" * 12):
        identity, problem = plc_identity.app_identity(raw)
        assert identity is None and "does not recognise" in problem, raw


# -- the working copy's files ---------------------------------------------

def test_the_working_copys_identities_are_read(tmp_path):
    project = project_in(tmp_path)
    write_info(project)
    assert plc_identity.local_identity(project, DEVICE, APPLICATION) == \
        (BOOTINFO_GUIDS, None)


def test_no_download_info_says_the_ide_will_download(tmp_path):
    project = project_in(tmp_path)
    identity, problem = plc_identity.local_identity(project, DEVICE,
                                                    APPLICATION)
    assert identity is None
    assert "softplc_refactor.%s.%s.<guid>.bootinfo_guids" % (
        DEVICE, APPLICATION) in problem
    assert "downloads the whole application" in problem
    assert "plc download -y" in problem


def test_two_candidates_are_listed_not_chosen_between(tmp_path):
    project = project_in(tmp_path)
    first = write_info(project)
    second = write_info(project, guid="00000000-0000-0000-0000-000000000000")
    identity, problem = plc_identity.local_identity(project, DEVICE,
                                                    APPLICATION)
    assert identity is None
    assert first in problem and second in problem


def test_a_missing_compileinfo_is_refused(tmp_path):
    project = project_in(tmp_path)
    write_info(project, compileinfo=False)
    identity, problem = plc_identity.local_identity(project, DEVICE,
                                                    APPLICATION)
    assert identity is None and ".compileinfo is missing" in problem


def test_a_guids_file_of_the_wrong_size_is_refused(tmp_path):
    project = project_in(tmp_path)
    write_info(project, guids=BOOTINFO_GUIDS[:31])
    identity, problem = plc_identity.local_identity(project, DEVICE,
                                                    APPLICATION)
    assert identity is None and "holds 31 bytes" in problem


def test_another_devices_or_applications_files_are_not_ours(tmp_path):
    project = project_in(tmp_path)
    write_info(project, device="Other")
    write_info(project, application="Application.Sub")
    identity, problem = plc_identity.local_identity(project, DEVICE,
                                                    APPLICATION)
    assert identity is None and "there is no" in problem


def test_brackets_in_a_name_are_not_a_pattern(tmp_path):
    # glob would read [1] as a character class and find nothing.
    project = project_in(tmp_path, "line[1].project")
    write_info(project, device="Dev[A]")
    assert plc_identity.local_identity(project, "Dev[A]", APPLICATION) == \
        (BOOTINFO_GUIDS, None)


# -- the verdict ------------------------------------------------------------

def test_agreeing_identities_give_the_code_identity(tmp_path):
    project = project_in(tmp_path)
    write_info(project)
    assert plc_identity.judged(APP_HEADER, project, DEVICE, APPLICATION) == \
        ("A438D017000000000000000000000000", None)


def test_differing_identities_show_both_sides_and_point_at_download(tmp_path):
    project = project_in(tmp_path)
    write_info(project)
    code, problem = plc_identity.judged(APP_HEADER_OLD, project, DEVICE,
                                        APPLICATION)
    assert code is None
    assert "different download than the controller holds" in problem
    assert "A438D017" in problem and "D3BA9E4A" in problem
    assert "plc download -y" in problem


def test_an_unreadable_header_is_judged_before_the_local_files(tmp_path):
    code, problem = plc_identity.judged(b"", project_in(tmp_path), DEVICE,
                                        APPLICATION)
    assert code is None and "does not recognise" in problem
