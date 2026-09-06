# -*- coding: utf-8 -*-
"""Drive a CODESYS-family IDE from the command line.

Every command has two forms and one meaning (SPEC D2). `--target X` talks to
the watcher inside an IDE somebody has open; `--project P --install I` starts
an IDE of its own, drives it and lets it go. They are mutually exclusive
because CODESYS will not open a project twice, so no run could want both.
`plc` is the one command with a single form, and cdsint/flags.py says why.

    cdsint installs
    cdsint list
    cdsint export  --target softplc
    cdsint verify  -y --project C:\\p\\line.project --install 3.5.21.40 \\
                   --sync-dir C:\\p\\exported
    cdsint plc connect --project C:\\p\\line.project --install 3.5.21.40

The work is elsewhere: cdsint/flags.py is the shape of the command line,
cdsint/target.py and cdsint/headless.py are the two forms, cdsint/verify.py
is the round trip, cdsint/report.py does the printing, cds/core/exits.py
holds SPEC 4.3's exit codes and cdsint/exits.py the exception that carries
one. This file is what becomes of a parsed command.
"""
from __future__ import print_function

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cds.core import ipc  # noqa: E402
from cds.core.exits import (EXIT_DENIED, EXIT_FAILED, EXIT_OK,  # noqa: E402,F401
                            EXIT_HEADLESS, EXIT_TARGET, EXIT_TIMEOUT)
from cdsint import flags, headless, installs, report, target, verify  # noqa: E402
from cdsint.exits import Failure  # noqa: E402

DEFAULT_TIMEOUT_S = flags.DEFAULT_TIMEOUT_S


# --------------------------------------------------------------------------
# Which form, and what to do with it
# --------------------------------------------------------------------------

def make_runner(ns):
    """The --target form or the --project form, both answering run(steps)."""
    if getattr(ns, "project", None):
        return headless.Headless(
            ns.project, ns.install, ns.profile, ns.report,
            answers=_answers(ns.answer), sync_dir=ns.sync_dir,
            timeout=ns.timeout, force_lock=ns.force_lock)
    flags.refuse_project_flags(ns)
    return target.Target(ipc.default_root(), ns.target, ns.timeout)


def _answers(pairs):
    found = {}
    for pair in pairs or []:
        key, sep, value = pair.partition("=")
        if not sep:
            raise Failure("--answer wants KEY=VALUE, not %r" % (pair,))
        found[key] = value
    return found


def run_installs(ns):
    report.show_installs(installs.find(), ns.json)
    return EXIT_OK


def run_list(ns):
    root = ipc.default_root()
    regs = target.live_instances(root, ns.timeout)
    if ns.json:
        report.as_json(regs)
        return EXIT_OK
    if not regs:
        # An empty list is the answer to "who is listening", not a failure,
        # so this is exit 0 (SPEC 4.3).
        print("no IDE is listening; start Project_watch.py in one")
        return EXIT_OK
    for reg in regs:
        print("%-28s %-6s %s" % (reg["instance_id"], reg.get("state", "?"),
                                 reg.get("project_path") or "(no project)"))
    return EXIT_OK


def run_verify(ns, runner):
    results, problems = verify.run(runner, getattr(ns, "yes", None))
    show_folder(ns, runner, results)
    report.show_steps(results, ns.json)
    for problem in problems:
        print("verify: " + problem, file=sys.stderr)
    if problems:
        return EXIT_FAILED
    print("verify: %s round-tripped and built cleanly" % runner.describe())
    return EXIT_OK


def run_command(ns, runner):
    results = runner.run([(flags.wire_name(ns), flags.command_args(ns))])
    show_folder(ns, runner, results)
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
    if not getattr(ns, "project", None):
        return
    for result in results:
        if result.get("sync_dir"):
            return report.show_sync_dir(result["sync_dir"], ns.json)
    return report.show_sync_dir(runner.sync_dir(), ns.json)


def exit_code(result):
    """What one result is worth as an exit code (SPEC 4.3).

    A refusal is not a failure and earns a code of its own: the reader's next
    move is a person editing the project's settings file, not another flag,
    and only exit 5 says that without the caller having to parse prose.
    """
    if result.get("ok"):
        return EXIT_OK
    if result.get("denied"):
        return EXIT_DENIED
    return EXIT_FAILED


def main(argv=None):
    parser = flags.build_parser()
    ns = parser.parse_args(argv)
    flags.check(parser, ns)
    try:
        if ns.command == "installs":
            return run_installs(ns)
        if ns.command == "list":
            return run_list(ns)
        runner = make_runner(ns)
        if ns.command == "verify":
            return run_verify(ns, runner)
        return run_command(ns, runner)
    except Failure as failure:
        return failure.report()


if __name__ == "__main__":
    sys.exit(main())
