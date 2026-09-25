# -*- coding: utf-8 -*-
"""Drive a CODESYS-family IDE from the command line.

Every command has two forms and one meaning (SPEC D2). `--target X` talks to
the watcher inside an IDE somebody has open; `--project P --install I` starts
an IDE of its own, drives it and lets it go. They are mutually exclusive
because CODESYS will not open a project twice, so no run could want both.
`plc` is the one command with a single form, and cdsint/flags.py says why.

    cdsint installs
    cdsint list
    cdsint update
    cdsint export  --target softplc
    cdsint verify  -y --project C:\\p\\line.project --install 3.5.21.40 \\
                   --sync-dir C:\\p\\exported
    cdsint plc connect --project C:\\p\\line.project --install 3.5.21.40
    cdsint plc trace --project C:\\p\\line.project --install 3.5.21.40 \\
                     --gateway 192.168.1.5 --job C:\\p\\trace.json

The work is elsewhere: cdsint/flags.py is the shape of the command line
and cdsint/refusals.py what it will not run, cdsint/job_file.py reads a
trace job before anything starts, cdsint/target.py and cdsint/headless.py
are the two forms, cdsint/verify.py is the round trip, cdsint/update.py
replaces a downloaded install and cdsint/release.py says when there is
something newer to replace it with, cdsint/report.py does
the printing, cds/core/exits.py holds SPEC 4.3's exit codes and
cdsint/exits.py the exception that carries one. This file is what becomes of
a parsed command.
"""
from __future__ import print_function

import os
import sys

# The install root. Needed by the one caller that reaches this file by path
# rather than by name: irm/setup.ps1 asks a fresh clone what is installed
# here, and at that moment nothing has been pip-installed yet. The console
# script and `python -m cdsint.cli` both arrive with the path already set up.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cds.core import ipc  # noqa: E402
from cds.core.exits import EXIT_DENIED, EXIT_FAILED, EXIT_OK  # noqa: E402
from cdsint import (  # noqa: E402
    flags, headless, installs, refusals, release, report, target, update,
    verify)
from cdsint.exits import Failure  # noqa: E402


# --------------------------------------------------------------------------
# Which form, and what to do with it
# --------------------------------------------------------------------------

def make_runner(ns):
    """The --target form or the --project form, both answering run(steps)."""
    if ns.project:
        return headless.Headless(
            ns.project, ns.install, ns.profile, ns.report,
            answers=dict(ns.answer), sync_dir=ns.sync_dir,
            timeout=ns.timeout, force_lock=ns.force_lock)
    return target.Target(ipc.default_root(), ns.target, ns.timeout)


def run_installs(ns):
    report.show_installs(installs.find(), ns.json)
    return EXIT_OK


def run_list(ns):
    regs = target.live_instances(ipc.default_root(), ns.timeout)
    report.show_instances(regs, ns.json)
    return EXIT_OK


def run_verify(ns, runner):
    results, problems = verify.run(runner, ns.yes)
    show_folder(ns, runner, results)
    report.show_notes(results, ns.json)
    report.show_steps(results, ns.json)
    report.show_verify(problems, runner.describe())
    return verify_code(results, problems)


def verify_code(results, problems):
    """Which of verify's results decides its exit code.

    The first step that failed, and then through the same door as a single
    command, because a step refused by the project's settings file is still a
    refusal and still earns exit 5 (SPEC 4.3) -- this used to answer 1 for
    that, which tells the reader to fix a flag when the fix is a word in a
    file. When every step came back ok and there are still problems, compare
    found differences after a round trip: nothing was refused and nothing
    crashed, so that is a plain failure.
    """
    for result in results:
        if not result["ok"]:
            return exit_code(result)
    return EXIT_FAILED if problems else EXIT_OK


def run_command(ns, runner):
    results = runner.run([(flags.wire_name(ns), flags.command_args(ns))])
    show_folder(ns, runner, results)
    report.show_notes(results, ns.json)
    report.show(results[0], ns.json)
    return exit_code(results[0])


def show_folder(ns, runner, results):
    """Name the folder a --project run treated as the truth (SPEC 4.2).

    Only that form. The --target form talks to an IDE somebody set up and has
    open; SPEC 4.2 puts this line in the --project section, and a line that
    suddenly appeared in front of `ping` would break anything reading the
    first one.

    The value comes from the result, because the IDE side is the only place
    that knows what the project's settings file said; from the runner when no
    step got far enough to report one, which is all a refused run has.
    """
    if not ns.project:
        return
    for result in results:
        if result.get("sync_dir"):
            return report.show_sync_dir(result["sync_dir"], ns.json)
    return report.show_sync_dir(runner.sync_dir(), ns.json)


def exit_code(result):
    """What one result is worth as an exit code (SPEC 4.3).

    The only place that decision is made. A refusal is not a failure and
    earns a code of its own: the reader's next move is a person editing the
    project's settings file, not another flag, and only exit 5 says that
    without the caller having to parse prose.
    """
    if result["ok"]:
        return EXIT_OK
    if result["denied"]:
        return EXIT_DENIED
    return EXIT_FAILED


# The commands that answer without an IDE: what is installed on this
# machine, who is listening, and replacing this install with a newer one.
# cdsint/flags.py says they take neither form; this says which function
# answers each.
ABOUT_THIS_MACHINE = {"installs": run_installs, "list": run_list,
                      "update": update.run}


def main(argv=None):
    parser = flags.build_parser()
    ns = parser.parse_args(argv)
    refusals.check(parser, ns)
    code = run(ns)
    release.remind(ns.command, ns.json)
    return code


def run(ns):
    """One parsed, accepted command line, to its exit code."""
    try:
        if flags.COMMANDS[ns.command].form == flags.NO_IDE:
            return ABOUT_THIS_MACHINE[ns.command](ns)
        runner = make_runner(ns)
        if ns.command == "verify":
            return run_verify(ns, runner)
        return run_command(ns, runner)
    except Failure as failure:
        return failure.report()


if __name__ == "__main__":
    sys.exit(main())
