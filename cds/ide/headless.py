# -*- coding: utf-8 -*-
"""The IDE side of a headless run: open the project, run the commands, report.

Started by cdsint/headless.py as

    <exe> --profile="<name>" --noUI --runscript="<this file>"

with CDSINT_HEADLESS_JOB naming a JSON file that says what to do. The job goes
through a file rather than --scriptargs because that flag is one string split
on spaces with quoting rules of its own, and these project paths have spaces
and Chinese in them (SPEC 6.4, "專案路徑走環境變數"). One variable naming one
file also keeps the two sides from growing a dozen variables between them.

The commands themselves run exactly as they do for the watcher — same bodies,
same stand-in UI answering the dialogs from the same flags — because that is
cds/ide/entries.py's job and this file only decides when to call it.

Nothing here waits: no sleep, no system.delay(), no timer (SPEC D5). The
script opens, runs, writes the report and returns, and the process ends
because there is nothing left holding it. Holding a headless IDE open for a
watcher is a different job and lives in tools/headless_watch.py.

IronPython 2.7: `system`, `projects` and the enum types come from the
caller's globals, and only the standard library is available.
"""
from __future__ import print_function

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    # Reached by path as a --runscript target, so nothing has put the install
    # root on the path yet.
    sys.path.insert(0, _ROOT)

from cds.core import commands, ipc, props   # noqa: E402
from cds.ide import entries, project, silent  # noqa: E402

JOB_ENV = "CDSINT_HEADLESS_JOB"

# Printed either side of the run. These exes are GUI-subsystem programs, so
# whether anything they print reaches a redirected handle at all is a fact
# about this machine, not something to assume — seeing both marks is how the
# CLI knows stdout came back rather than the file merely existing (SPEC 6.4).
BEGIN_MARK = "=== CDSINT_HEADLESS_BEGIN ==="
END_MARK = "=== CDSINT_HEADLESS_END ==="

# What the CLI compares against the exit code it actually received. If they
# disagree the exit code cannot be used as a gate and the report is the only
# answer (SPEC 6.4).
EXIT_OK = 0
EXIT_FAILED = 1

def main(ide_globals, job_path=None):
    """Do one job and write its report. Returns the exit code it asked for."""
    print(BEGIN_MARK)
    try:
        job = ipc.read_json(job_path or os.environ.get(JOB_ENV, ""))
        if job is None:
            print("headless: no job file; set %s" % JOB_ENV)
            return EXIT_FAILED
        report = run_job(ide_globals, job)
        ipc.write_json(job["report"], report)
        print("headless: report written to " + job["report"])
        return report["intended_exit"]
    finally:
        print(END_MARK)


def run_job(ide_globals, job):
    """Open the project, run every command, and build the report record."""
    report = {
        "ide": project.ide_name(),
        "project": job.get("project"),
        "results": [],
        "error": None,
        "opened": False,
        "intended_exit": EXIT_FAILED,
    }
    answer_prompts(ide_globals, job.get("answers"))
    try:
        opened = open_project(ide_globals, job["project"])
    except Exception:
        import traceback
        report["error"] = (_why_nothing_opened(job) + "\n\n"
                           + traceback.format_exc())
        return report
    if opened is None:
        report["error"] = _why_nothing_opened(job)
        return report
    report["opened"] = True
    report["project"] = _text(getattr(opened, "path", job.get("project")))
    if job.get("sync_dir"):
        point_sync_folder(ide_globals.get("projects"), job["sync_dir"])
    report["results"] = run_commands(ide_globals, job.get("commands") or [])
    if all(result["ok"] for result in report["results"]):
        report["intended_exit"] = EXIT_OK
    return report


def run_commands(ide_globals, wanted):
    """Run each command in turn, stopping at the first one that fails.

    Carrying on after a failed import would export whatever half-imported
    state the project is in and call the round trip clean.
    """
    results = []
    for step in wanted:
        results.append(run_one(ide_globals, step["command"],
                               step.get("args") or {}))
        if not results[-1]["ok"]:
            break
    return results


def run_one(ide_globals, command, args):
    """One command, as the same result record the watcher writes."""
    cmd = {"id": commands.new_id(), "command": command, "args": args}
    started = ipc.now()
    try:
        outcome = entries.run(ide_globals, command, args)
    except silent.NeedsInput as need:
        return commands.new_result(cmd, False, started_at=started,
                                   error=need.question,
                                   needs_input=need.as_record())
    except Exception:
        import traceback
        return commands.new_result(cmd, False, started_at=started,
                                   error=traceback.format_exc())
    error = (outcome.error_text()
             or entries.wrong_application(command, args, outcome))
    return commands.new_result(
        cmd, not error, started_at=started, error=error,
        messages=outcome.messages,
        stdout_tail=entries.tail(ide_globals, command, outcome),
        data=outcome.data(),
        denied=outcome.denied,
        needs_input=None if outcome.needs is None else outcome.needs.as_record())


def answer_prompts(ide_globals, answers=None):
    """Fill in the IDE's own prompts, and name the ones nobody filled in.

    These are the IDE's dialogs, not cdsint's, so D7's "never guess" does not
    reach them — but the exception is only honest if an unanswered one is
    visible. LogMessageKeys prints the key and the full text of every prompt,
    so a run that stopped on one says which --answer would have got past it.

    Deliberately no defaults. The upgrade prompt in particular rewrites the
    project's storage format, and after that the IDE it came from cannot open
    it again; answering Yes on the caller's behalf would do that silently to
    a project they only asked to build.
    """
    system = ide_globals["system"]
    handling = ide_globals["PromptHandling"]
    result = ide_globals["PromptResult"]
    system.prompt_handling = (handling.LogMessageKeys |
                              handling.LogSimplePrompts |
                              handling.ProcessScriptPrompts)
    for key, answer in sorted((answers or {}).items()):
        system.prompt_answers[key] = getattr(result, answer)
    return system.prompt_answers


def open_project(ide_globals, path):
    """Open a project with nobody there to answer for it.

    Deliberately not the handle open() returned. Upgrading the storage format
    closes and reopens the project underneath, and the old handle then throws
    NullReferenceException on its first use — Delta 1.10 does exactly that on
    save(). `primary` is whatever is open now.

    Password arguments are not passed at all: an encrypted project or one
    with user management fails here rather than prompting, and failing is the
    right answer, because credentials are not this tool's business (D14).
    """
    ide_globals["projects"].open(path)
    return ide_globals["projects"].primary


def point_sync_folder(projects_obj, sync_dir):
    """Set cds-sync-folder for this run. Absolute, so nothing is ambiguous.

    Not saved: the caller asked where the .st files are for this run, not to
    change the project on disk. `cdsint config set` is how you change it for
    good.
    """
    return project.set_prop(projects_obj, props.FOLDER, sync_dir)


def _why_nothing_opened(job):
    """The open produced no project, which is what a cancelled prompt does.

    Cancelling shows up two ways — open() returning nothing, and it throwing
    "Do not upgrade the older version project" — and both mean the same
    thing, so both get told the same thing. The keys are on stdout thanks to
    LogMessageKeys, but naming the likely one saves a reader the hunt.
    """
    return ("%s did not open. A prompt this run had no answer for is the "
            "usual reason — the keys are on stdout, and --answer KEY=VALUE "
            "answers them. A project saved by an older IDE asks "
            "UpgradeProjectConfirmation, and saying Yes rewrites its storage "
            "format so that older IDE can no longer open it, which is why "
            "nothing here answers it for you."
            % (job.get("project"),))


def _text(value):
    """Bytes or unicode in, something json.dumps will take out."""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return None if value is None else type(u"")(value)


if __name__ == "__main__":
    # CODESYS runs a --runscript file as __main__ with its own objects already
    # in this namespace, which is why the globals are passed rather than
    # imported. The report is written before the exit so a caller that only
    # gets a killed process still has the answer.
    sys.exit(main(globals()))
