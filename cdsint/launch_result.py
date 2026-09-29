# -*- coding: utf-8 -*-
"""What a headless launch came back with: its report, completed and judged.

cdsint/headless.py starts the IDE and waits; this is the other half, what
it makes of the process it waited for. The IDE side's report is the account
of the work. What only the outside knows -- the exit code the shell saw,
whether the process had to be killed, whether stdout came back at all -- is
added here, and then the whole is turned into results or into the Failure
that says why there are none (SPEC 6.4).

`launch`, wherever it is taken, is the Headless whose run this is.
"""
from __future__ import print_function

from cds.core.exits import EXIT_HEADLESS, EXIT_TIMEOUT
from cds.ide.headless import BEGIN_MARK, END_MARK, also
from cdsint.exits import Failure
from cdsint.report import untrusted_exit

# A full download stops the application before it writes, so a kill anywhere
# after its login can leave the controller stopped, or holding half a program.
KILLED_DOWNLOAD = ("plc download was in this run: the controller may now be "
                   "stopped or partly written; check it before trusting it.")


def annotate(launch, report, code, pid, elapsed, deadline):
    """The fields only this side of the launch can fill in (SPEC 6.4).

    The IDE side puts intended_exit in its report only after every command
    has been run, so a report carrying it is the script's own account of a
    finished run — and that outranks anything the exit code says
    afterwards. Whether the exit code can be used as a gate is therefore
    a fact to measure, not to assume: the script writes down the code it
    meant to use and this compares.
    """
    finished = report.get("intended_exit") is not None
    added = {
        "install": launch.install["name"], "profile": launch.profile,
        "report_path": launch.report_path,
        # The IDE side's value if it got that far, because that is the
        # folder the engine read; the flag only says what was asked for.
        "sync_dir": report.get("sync_dir") or launch.sync_dir(),
        "elapsed_s": round(elapsed, 3),
        "pid": pid, "exit_code_actual": code, "timed_out": code is None,
        "stdout_path": launch.stdout_path(),
        "stderr_path": launch.stderr_path(),
        "stdout_reached": stdout_reached(launch),
        "exit_code_trusted": finished and code == report.get("intended_exit"),
    }
    if code is None:
        added["error"] = also(report.get("error"),
                              late_exit(launch, pid, deadline) if finished
                              else timed_out(launch, pid, deadline))
    return added


def verdict(launch, report, code):
    """The results, or the reason there are none. Says each thing once.

    A killed run's sentence is either the Failure's message or a note,
    never both: cdsint/exits.py prints a Failure's message, so a note with
    the same text would be read twice.
    Which of the two it is depends on whether the work got done — a
    report with an intended_exit is the answer, and a kill that came
    after it is only a slow shutdown (SPEC 6.4).

    A Failure carries the notes with it. There are no results on that
    path, so nothing else would ever say them, and they are exactly what
    the reader needs: a run that was killed is also a run whose lock file
    somebody has to account for.
    """
    if report.get("intended_exit") is None:
        # Killed before the end, or ended without finishing its report;
        # a report that only says the project opened is not an answer.
        raise Failure(report.get("error")
                      or "the IDE ran but did not finish its report; see "
                         + launch.stdout_path(),
                      EXIT_TIMEOUT if code is None else EXIT_HEADLESS,
                      launch.notes)
    if code is None:
        launch.note(report["error"])
    else:
        launch.note(untrusted_exit(report))
    if not report.get("opened"):
        raise Failure(report.get("error") or "the project did not open",
                      EXIT_HEADLESS, launch.notes)
    for result in report["results"]:
        # SPEC 4.3: the --project form's record says which IDE ran it,
        # which folder it took for the truth, and where the rest of the
        # story is. The notes ride along for the same reason: a --json
        # caller has no other way to hear about a lock we cleared.
        result["ide"] = report.get("ide")
        result["report_path"] = launch.report_path
        result["sync_dir"] = report.get("sync_dir")
        result["notes"] = list(launch.notes)
    return report["results"]


def timed_out(launch, pid, deadline):
    """The conclusion, not just the symptom, and it goes in the report.

    A caller reading only the report file has to find "this hung" there,
    because the exit code it would otherwise reason from is the one thing
    a killed process cannot give it. This is the half of the kill with no
    report behind it, so the work itself is unaccounted for.
    """
    said = ("%s did not finish within %gs and was killed (pid %s) before "
            "it finished its report. Under --noUI that usually means a "
            "dialog opened with nothing to close it; %s has what it was "
            "doing."
            % (launch.install["name"], deadline, pid, launch.stdout_path()))
    # A download's unaccounted work is on a controller.
    return also(said, KILLED_DOWNLOAD) if launch.downloading else said


def late_exit(launch, pid, deadline):
    """Killed, but the work was already done and written down.

    A report with an intended_exit means every command ran and the script
    returned; what outlived the deadline was the IDE's own shutdown.
    Calling that a timeout would throw away the answer the run produced,
    which is the whole point of writing the report before exiting.
    """
    return ("%s finished the work and wrote its report, then did not exit "
            "within %gs and was killed (pid %s). The report is the answer; "
            "the exit code is not."
            % (launch.install["name"], deadline, pid))


def stdout_reached(launch):
    """Both marks, not just the file: half the output is not the output."""
    try:
        with open(launch.stdout_path(), "rb") as handle:
            text = handle.read().decode("utf-8", "replace")
    except (IOError, OSError):
        return False
    return BEGIN_MARK in text and END_MARK in text
