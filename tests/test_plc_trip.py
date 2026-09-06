# -*- coding: utf-8 -*-
"""One trip to a controller, end to end, and the verdict it comes back with.

The comparison is the whole point of the pair (SPEC 6.6) — but not the
obvious comparison. An offline boot application and the one on the
controller are different artefacts and never match, and the offline one
moves every run besides; engine/plc_crc.py holds the bench measurements
that say so. What is compared is the CRC the controller holds now against
the one a download from this project left there. MATCH is the only answer
that passes, because a caller reading the exit code has to be able to tell
"it is still running what I put there" from "it might be running anything".

Everything here runs against stand-in IDE objects; the controller itself
needs a person at a bench.
"""
import os

from cds.ide import silent
from engine import plc_crc as plc_crc_module
import tests.plc_fakes as plc_fakes
from tests.plc_fakes import (CRC_A, CRC_B, CRC_C, Device, Gateway,
                             PLC_BODY, Session, ide, recorded)
from tests.plc_fakes import (   # noqa: F401  autouse fixtures
    fake_codesys_ui, keep_the_engine_loaded, workspace)


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
        plc_crc_module.record_path(plc_fakes.PROJECT_PATH))["project"]
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
        plc_crc_module.record_path(plc_fakes.PROJECT_PATH)) == {}


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
