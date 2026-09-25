# -*- coding: utf-8 -*-
"""plc trace, end to end on a fake bench: every refusal by name, and one good run.

SPEC 6.8 is the run. Each refusal below is a thing a bench run showed goes
wrong silently without it (docs/trace-research.md), so each is pinned by the
sentence a reader gets and by what did NOT happen after it: no login, no
download, no trace object.

The recording holds on a fake clock that moves only when the run holds, so
a run of any duration takes no real time, and the count of holds is the
check that the loop waits as long as it was asked to and no longer.

What only a person at a bench can confirm -- that the real trace plug-in
takes these calls, and that the private member sets the buffers -- is not
claimed here.
"""
import os

from cds.core import trace_run
from cds.ide import headless, hold
from engine import plc_trace
from tests.fakes import FakeSystem
from tests.plc_fakes import (GATEWAY, PORT, TASK, TRACED, Buffers,
                             TraceBench, gapped_csv, press, read_data,
                             TASK_CONFIG_XML)
from tests.plc_fakes import (   # noqa: F401  autouse fixtures
    fake_codesys_ui, keep_the_engine_loaded, workspace)
import tests.plc_fakes as plc_fakes

OVERWRITE = "Strings.OverwriteExistingOnlineTrace"


def nothing_was_created(bench):
    return bench.tracer.created == []


def nothing_was_downloaded(bench):
    return bench.calls("download", "start") == []


# --------------------------------------------------------------------------
# The good run
# --------------------------------------------------------------------------

def test_a_good_run_records_saves_and_passes():
    bench = TraceBench()
    result = bench.run()
    assert result["ok"], result["summary"]
    data = result["data"]
    assert data["crc"] == "MATCH" and data["complete"] is True
    assert data["why"] is None and data["failed_objects"] == []
    out = plc_fakes.trace_job()["out"]
    assert data["files"] == {"trace": out + ".trace", "csv": out + ".csv"}
    assert all(os.path.isfile(path) for path in data["files"].values())


def test_the_calls_come_in_the_order_spec_6_8_gives():
    bench = TraceBench()
    bench.run()
    order = [call[0] for call in bench.log if call[0] != "hold"]
    assert order == [
        "create", "login", "read_value", "read_value", "open_editor",
        "answer set", "download", "answer removed", "start", "stop",
        "save", "save", "logout"]
    assert ("login", "keep", False) in bench.log


def test_the_overwrite_prompt_is_answered_around_the_download_only():
    # D7: set by the trace step and gone right after, so no other command
    # in the run inherits it.
    bench = TraceBench()
    ide_globals = bench.globals()
    from engine import entry_plc
    from engine.plc_trace import TraceTrip
    entry_plc.traced(TraceTrip(bench.args(), ide_globals, clock=bench.clock,
                               buffers_for=bench.buffers))
    assert ("answer set", OVERWRITE, "ok") in bench.log
    assert ("answer removed", OVERWRITE) in bench.log
    assert OVERWRITE not in ide_globals["system"].prompt_answers


def test_the_body_reaches_the_ide_trace_plug_in_through_the_real_load_path():
    # The bench found it: entry_plc.py is exec'd into the IDE's own namespace,
    # and an entry function called trace() shadowed the `trace` plug-in the
    # trip borrows by that name. Through silent.run, the exec path the IDE
    # takes, create() has to land on the plug-in, whatever the body's
    # functions are called. clr is absent under CPython, so the run stops
    # right after create(); reaching create() is the whole test.
    from cds.ide import silent
    from tests.plc_fakes import PLC_BODY
    bench = TraceBench()
    silent.run(bench.globals(), PLC_BODY, "record", bench.args())
    assert bench.tracer.created and bench.tracer.created[0][1] == "cdsint_trace"


def test_the_trace_is_configured_from_the_job_and_the_task_period():
    bench = TraceBench()
    data = bench.run(plc_fakes.trace_job(every_n_cycles=2))["data"]
    api = bench.tracer.api
    assert bench.tracer.created[0][1:] == ("cdsint_trace", TASK)
    assert api.variables == TRACED
    assert api.resolution == "microseconds" and api.every_n_cycles == 2
    ring, per_variable = trace_run.buffers(1000, 2, 1.0)
    assert bench.buffers.set_to == (ring, per_variable)
    # UDINT and INT: 12 + 4 + 2 bytes an entry
    assert data["buffer"] == {"controller_entries": ring,
                              "controller_bytes": ring * 18,
                              "ide_per_variable": per_variable}
    assert data["period_us"] == 1000
    # recursive, because the tasks are children of the configuration
    assert bench.project.exported[1] is True


def test_the_millisecond_resolution_reaches_the_trace():
    bench = TraceBench()
    bench.run(plc_fakes.trace_job(resolution="ms"))
    assert bench.tracer.api.resolution == "milliseconds"


def test_the_report_has_exactly_the_spec_shape():
    data = TraceBench().run()["data"]
    assert set(data) == {
        "action", "controller", "crc", "task", "period_us", "resolution",
        "duration_s", "buffer", "files", "variables", "complete",
        "failed_objects", "why", "notes", "workspace"}
    assert data["action"] == "trace"
    assert data["controller"] == "%s:%d" % (GATEWAY, PORT)
    assert data["resolution"] == "us" and data["task"] == TASK
    row = data["variables"][1]
    assert row["name"] == "PRG_AxisControl._iOvrZone"
    assert row["type"] == "INT" and row["gaps"] == []
    assert data["variables"][0]["type"] == "UDINT"


def test_the_project_is_never_saved():
    bench = TraceBench()
    bench.run()
    assert bench.project.saves == 0


def test_the_csv_goes_to_the_workspace_when_the_job_did_not_ask_for_it():
    bench = TraceBench()
    result = bench.run(plc_fakes.trace_job(formats=["trace"]))
    assert result["ok"], result["summary"]
    out = plc_fakes.trace_job()["out"]
    assert result["data"]["files"] == {"trace": out + ".trace"}
    saved = [call[1] for call in bench.calls("save")]
    in_workspace = os.path.join(result["data"]["workspace"],
                                plc_trace.WORKSPACE_CSV)
    assert in_workspace in saved
    assert not os.path.exists(out + ".csv")


# --------------------------------------------------------------------------
# The wait
# --------------------------------------------------------------------------

def test_the_recording_holds_for_the_duration_and_no_longer():
    bench = TraceBench()
    bench.run(plc_fakes.trace_job(duration_s=3.0))
    holds = bench.calls("hold")
    assert len(holds) == 15
    assert set(holds) == {("hold", trace_run.HOLD_MS)}
    # between start and stop, not anywhere else
    kinds = [call[0] for call in bench.log]
    assert kinds.index("start") < kinds.index("hold")
    assert kinds.index("stop") == max(i for i, k in enumerate(kinds)
                                      if k == "hold") + 1


def test_with_a_window_there_is_no_hold_and_the_run_refuses():
    bench = TraceBench()
    result = bench.run(ui=True)
    assert not result["ok"]
    assert "cannot wait" in result["summary"] and "D5" in result["summary"]
    assert bench.log == []


def test_the_hold_exists_only_without_a_ui():
    class Headless(FakeSystem):
        ui_present = False

        def __init__(self):
            FakeSystem.__init__(self)
            self.delays = []

        def delay(self, milliseconds):
            self.delays.append(milliseconds)

    class Windowed(FakeSystem):
        ui_present = True

    assert hold.hold_for(Windowed()) is None
    # an IDE that does not say is treated as having a window
    assert hold.hold_for(FakeSystem()) is None
    system = Headless()
    hold.hold_for(system)(200)
    assert system.delays == [200]


def test_a_headless_run_lends_the_hold_under_the_shared_name():
    class Headless(FakeSystem):
        ui_present = False

    ide_globals = {"system": Headless()}
    headless.run_commands(ide_globals, [])
    assert callable(ide_globals[trace_run.HOLD_GLOBAL])


# --------------------------------------------------------------------------
# Refusals, each by name, each before the thing it guards
# --------------------------------------------------------------------------

def test_without_a_gateway_nothing_is_touched():
    bench = TraceBench()
    result = bench.run(gateway=None)
    assert not result["ok"] and "--gateway" in result["summary"]
    assert bench.log == [] and bench.online.credentials is None


def test_the_body_is_reached_by_its_command_name():
    # Through cds/ide/entries.py, the way the headless launcher presses it.
    bench = TraceBench()
    outcome = press(bench.globals(), "trace", bench.args(gateway=""))
    assert not outcome.ok()
    assert "--gateway" in outcome.error_text()


def test_a_project_that_does_not_allow_trace_never_starts_it():
    bench = TraceBench()
    ide_globals = bench.globals()
    from cds.core import settings
    settings.write(settings.path_for(plc_fakes.PROJECT_PATH),
                   {"plc": ["connect"]})
    outcome = press(ide_globals, "trace", bench.args())
    assert outcome.denied and bench.log == []


def test_a_job_the_ide_side_cannot_read_is_refused():
    bench = TraceBench()
    job = plc_fakes.trace_job(trigger="x")
    result = bench.run(job)
    assert not result["ok"] and "trigger" in result["summary"]
    assert nothing_was_created(bench)


def test_a_controller_loaded_with_something_else_points_at_download():
    bench = TraceBench(record="DEADBEEF")
    result = bench.run()
    assert not result["ok"] and result["data"]["crc"] == "DIFFERENT"
    assert "plc download -y" in result["summary"]
    assert nothing_was_created(bench) and bench.calls("login") == []


def test_a_controller_never_downloaded_from_here_points_at_download():
    bench = TraceBench(record=None)
    result = bench.run()
    assert result["data"]["crc"] == "UNKNOWN"
    assert "plc download -y" in result["summary"]
    assert nothing_was_created(bench)


def test_the_download_info_agreeing_is_noted_with_the_code_identity():
    result = TraceBench().run()
    assert ("download info agrees with the controller: code "
            "A438D017000000000000000000000000") in result["data"]["notes"]


def test_missing_download_info_is_refused_before_any_login():
    # The bench: a Keep login on a copy with only its .project downloaded
    # the whole application, under a CRC record that said MATCH.
    bench = TraceBench(guids=None)
    result = bench.run()
    assert not result["ok"]
    assert ".bootinfo_guids" in result["summary"]
    assert "downloads the whole application" in result["summary"]
    assert "plc download -y" in result["summary"]
    assert bench.calls("login") == [] and nothing_was_created(bench)


def test_download_info_for_another_download_is_refused_before_any_login():
    bench = TraceBench(app=plc_fakes.APP_HEADER_OLD)
    result = bench.run()
    assert not result["ok"]
    assert "different download than the controller holds" in         result["summary"]
    assert "plc download -y" in result["summary"]
    assert bench.calls("login") == [] and nothing_was_created(bench)


def test_an_app_header_in_an_unknown_layout_is_refused():
    header = bytearray(plc_fakes.APP_HEADER)
    header[0x14] = 0x72
    bench = TraceBench(app=bytes(header))
    result = bench.run()
    assert not result["ok"] and "does not recognise" in result["summary"]
    assert bench.calls("login") == [] and nothing_was_created(bench)


def test_a_controller_without_an_app_is_refused():
    bench = TraceBench(app=None)
    result = bench.run()
    assert not result["ok"]
    assert "Application.app could not be fetched" in result["summary"]
    assert bench.calls("login") == [] and nothing_was_created(bench)


def test_a_program_that_differs_from_the_download_is_refused_before_login():
    # The bench: with the download info in place, a Keep login on a copy
    # edited in memory made an online change, and a changed master cycle
    # made a full download that left the application stopped
    # (docs/ethercat-research.md 5.2).
    bench = TraceBench()
    bench.application.is_uptodate = False
    result = bench.run()
    assert not result["ok"]
    assert "differs from what was last downloaded" in result["summary"]
    assert "online change or a full download" in result["summary"]
    assert "plc download -y" in result["summary"]
    assert bench.calls("login") == [] and nothing_was_created(bench)


def test_an_ide_that_cannot_say_whether_the_program_changed_is_refused():
    bench = TraceBench()
    del bench.application.is_uptodate
    result = bench.run()
    assert not result["ok"] and "is_uptodate" in result["summary"]
    assert bench.calls("login") == [] and nothing_was_created(bench)


def test_a_project_without_an_active_application_is_refused():
    bench = TraceBench()
    bench.project.active_application = None
    result = bench.run()
    assert not result["ok"] and "no active application" in result["summary"]
    assert bench.calls("login") == [] and nothing_was_created(bench)


def test_a_task_that_does_not_exist_is_refused_by_name():
    bench = TraceBench()
    result = bench.run(plc_fakes.trace_job(task="NoSuchTask"))
    assert not result["ok"]
    assert "NoSuchTask" in result["summary"] and TASK in result["summary"]
    assert nothing_was_created(bench)


def test_a_task_that_is_not_cyclic_is_refused():
    xml = read_data(TASK_CONFIG_XML).replace(u">Cyclic<", u">Freewheeling<")
    bench = TraceBench(xml=xml)
    result = bench.run()
    assert not result["ok"] and "Freewheeling" in result["summary"]
    assert nothing_was_created(bench)


def test_an_application_without_a_task_configuration_is_refused():
    bench = TraceBench()
    bench.application._children = []
    result = bench.run()
    assert not result["ok"] and "task configuration" in result["summary"]
    assert nothing_was_created(bench)


def test_an_existing_cdsint_trace_is_refused_not_renamed_around():
    bench = TraceBench(names=["CDSINT_trace"])
    result = bench.run()
    assert not result["ok"]
    assert "already has an object named cdsint_trace" in result["summary"]
    assert nothing_was_created(bench)


def test_an_ide_without_the_private_member_records_nothing():
    bench = TraceBench()
    bench.buffers = Buffers(present=False)
    result = bench.run()
    assert not result["ok"]
    assert "PerformWithWriteableCopy" in result["summary"]
    assert bench.calls("login") == [] and bench.tracer.api.variables == []


def test_another_client_logged_in_is_said_as_that():
    words = ("A login is currently not possible. The user 'kevin' is "
             "already logged in from host 'x' via 'CODESYS'.")
    bench = TraceBench(refuse_login=words)
    result = bench.run()
    assert not result["ok"]
    assert "another client is logged in" in result["summary"]
    assert "kevin" in result["summary"]      # the IDE's own words, carried
    # not "project differs", or the reader goes and downloads for nothing
    assert "differ" not in result["summary"].split("The IDE said")[0]
    assert nothing_was_downloaded(bench) and bench.calls("logout")


def test_any_other_login_refusal_carries_the_ides_words():
    bench = TraceBench(refuse_login="the controller said no")
    result = bench.run()
    assert "the login was refused: the controller said no" in \
        result["summary"]
    assert bench.calls("logout")


def test_a_name_the_controller_does_not_have_is_a_failed_object():
    values = {"PRG_AxisControl._uFlags": "UDINT#0"}
    bench = TraceBench(values=values)
    result = bench.run()
    assert not result["ok"]
    assert result["data"]["failed_objects"] == ["PRG_AxisControl._iOvrZone"]
    assert "PRG_AxisControl._iOvrZone (Invalid expression)" in \
        result["summary"]
    assert nothing_was_downloaded(bench) and bench.calls("open_editor") == []
    assert bench.calls("logout")


def test_a_stopped_application_is_refused_and_not_started():
    bench = TraceBench(state="stop")
    result = bench.run()
    assert not result["ok"]
    assert "stop" in result["summary"] and "does not start it" in \
        result["summary"]
    assert nothing_was_downloaded(bench) and bench.calls("logout")


# --------------------------------------------------------------------------
# Short of samples
# --------------------------------------------------------------------------

def test_lost_samples_fail_the_run_and_the_files_stay():
    bench = TraceBench(csv_text=gapped_csv())
    result = bench.run()
    data = result["data"]
    assert not result["ok"] and data["complete"] is False
    assert all(os.path.isfile(path) for path in data["files"].values())
    assert "PRG_AxisControl._uFlags" in result["summary"]
    assert "PRG_AxisControl._iOvrZone" not in result["summary"]
    assert data["why"] and "samples are missing" in data["why"]
    assert "cycles the controller did not run" in data["why"]


def test_a_csv_with_no_variables_is_not_complete():
    header = u"".join(line for line in read_data(plc_fakes.SAMPLE_CSV)
                      .splitlines(True) if u"Variable" not in line
                      and not line.startswith(u";")
                      and not line[:1].isdigit())
    bench = TraceBench(csv_text=header)
    result = bench.run()
    assert not result["ok"] and "no variables" in result["summary"]
