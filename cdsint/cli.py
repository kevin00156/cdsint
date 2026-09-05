# -*- coding: utf-8 -*-
"""Drive a CODESYS-family IDE from the command line.

Every command has two forms and one meaning (SPEC D2). `--target X` talks to
the watcher inside an IDE somebody has open; `--project P --install I` starts
an IDE of its own, drives it and lets it go. They are mutually exclusive
because CODESYS will not open a project twice, so no run could want both.

    cdsint installs
    cdsint list
    cdsint export  --target softplc
    cdsint verify  -y --project C:\\p\\line.project --install 3.5.21.40 \\
                   --sync-dir C:\\p\\exported
    cdsint config set cds-sync-debug=true --target softplc

The work is elsewhere: cdsint/target.py and cdsint/headless.py are the two
forms, cdsint/verify.py is the round trip, cdsint/report.py does the printing
and cdsint/exits.py holds SPEC 4.3's exit codes. This file is the surface.
"""
from __future__ import print_function

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cds.core import ipc  # noqa: E402
from cdsint import headless, installs, report, target, verify  # noqa: E402
from cdsint.exits import (EXIT_FAILED, EXIT_OK, EXIT_TARGET, EXIT_TIMEOUT,  # noqa: E402,F401
                          EXIT_HEADLESS, Failure)

DEFAULT_TIMEOUT_S = target.DEFAULT_TIMEOUT_S

_HELP = {
    "installs": "list the IDEs on this machine, and what to call each one",
    "list": "show the IDEs that are listening",
    "ping": "check that an IDE is answering",
    "status": "show what an IDE has open right now",
    "export": "write the project out to the sync folder",
    "import": "read the sync folder back into the project",
    "compare": "report how the project and the sync folder differ",
    "build": "build the application and report the error count",
    "verify": "import (-y), export, compare and build, and pass only if all "
              "agree",
    "config": "read or write the project's cds-sync-* properties",
    "stop": "tell a watcher to shut down",
}

# Commands that need an IDE with the project open, in either form.
BOTH_FORMS = ("export", "import", "compare", "build", "verify", "config")
# Commands about a watcher's life, which only the --target form has.
WATCHER_ONLY = ("ping", "status", "stop")

# Extra flags per command, and how they become the command's args. A flag left
# out arrives as None so the watcher can tell "not said" from "said no".
FLAGS = {
    "export": [("--delete-orphans", "delete the sync files with no object behind them")],
    "import": [("--yes", "confirm the import; without it the watcher asks"),
               ("--force", "go ahead despite a version or computer mismatch")],
    "build": [("--app", "which application to build, when there are several")],
    "verify": [("--yes", "confirm the import step; without it verify only "
                         "looks and says what the import would have done"),
               ("--force", "go ahead despite a version or computer mismatch")],
}

# Only meaningful when we start the IDE ourselves. --answer is among them
# because the prompts it answers are the IDE's own, and in the --target form
# there is a person sitting in front of that IDE to answer them.
PROJECT_ONLY = ("install", "profile", "report", "force_lock", "sync_dir",
                "answer")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="cdsint", description="Drive a CODESYS-family IDE.")
    sub = parser.add_subparsers(dest="command", required=True)
    _shared(sub.add_parser("installs", help=_HELP["installs"]))
    _shared(sub.add_parser("list", help=_HELP["list"]))
    for name in WATCHER_ONLY:
        _target_flag(_shared(sub.add_parser(name, help=_HELP[name])))
    for name in BOTH_FORMS:
        command = _both_forms(_shared(sub.add_parser(name, help=_HELP[name])))
        for flag, help_text in FLAGS.get(name, []):
            _add_flag(command, flag, help_text)
    _config_arguments(sub.choices["config"])
    return parser


def _shared(parser):
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S,
                        help="seconds to wait for the answer (default 120); "
                             "also how long a busy IDE counts as alive")
    parser.add_argument("--json", action="store_true",
                        help="print the raw record instead of a summary")
    return parser


def _target_flag(parser):
    parser.add_argument("--target", help="instance id, or a project name")
    return parser


def _both_forms(parser):
    """The two forms, and the flags that only make sense in the second one."""
    form = parser.add_mutually_exclusive_group()
    form.add_argument("--target", help="instance id, or a project name of a "
                                       "watcher that is already listening")
    form.add_argument("--project", help="a .project to open in an IDE of our "
                                        "own; needs --install")
    parser.add_argument("--install", help="which IDE to start; `cdsint "
                                          "installs` lists them")
    parser.add_argument("--profile", help="the IDE profile name, when the "
                                          "install has more than one")
    parser.add_argument("--report", help="where to write the run's report")
    parser.add_argument("--force-lock", action="store_true",
                        help="start even though the project looks open elsewhere")
    parser.add_argument("--sync-dir", help="use this sync folder for the run")
    parser.add_argument("--answer", action="append", default=[],
                        metavar="KEY=VALUE",
                        help="answer one of the IDE's own prompts; repeatable")
    return parser


def _add_flag(command, flag, help_text):
    if flag == "--app":
        return command.add_argument(flag, default=None, help=help_text)
    if flag == "--yes":
        # -y is the spelling in SPEC 4.2, and the one every other tool that
        # asks "are you sure" uses.
        return command.add_argument("-y", flag, action="store_true",
                                    default=None, help=help_text)
    return command.add_argument(flag, action="store_true", default=None,
                                help=help_text)


def _config_arguments(parser):
    parser.add_argument("action", choices=("get", "set"),
                        help="read a property, or write one")
    parser.add_argument("setting", nargs="?", metavar="KEY[=VALUE]",
                        help="the property; get takes a name and set takes "
                             "KEY=VALUE. get with no name lists them all")


def command_args(ns):
    """Turn the parsed flags back into the args the IDE side reads."""
    if ns.command == "config":
        return _config_args(ns)
    return dict((flag.lstrip("-").replace("-", "_"),
                 getattr(ns, flag.lstrip("-").replace("-", "_")))
                for flag, _ in FLAGS.get(ns.command, []))


def _config_args(ns):
    if ns.action == "get":
        return {"key": ns.setting, "value": None}
    key, _, value = (ns.setting or "").partition("=")
    return {"key": key or None, "value": value}


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
    _refuse_project_flags(ns)
    return target.Target(ipc.default_root(), ns.target, ns.timeout)


def _refuse_project_flags(ns):
    """A --project flag with no --project is a caller who thinks it is headless.

    Ignoring it would run the command against somebody's open IDE while the
    caller believed it was driving one of its own.
    """
    given = [name for name in PROJECT_ONLY if getattr(ns, name, None)]
    if given:
        raise Failure("--%s only works with --project"
                      % given[0].replace("_", "-"))


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
    results, problems = verify.run(runner, getattr(ns, "force", None),
                                   getattr(ns, "yes", None))
    report.show_steps(results, ns.json)
    for problem in problems:
        print("verify: " + problem, file=sys.stderr)
    if problems:
        return EXIT_FAILED
    print("verify: %s round-tripped and built cleanly" % runner.describe())
    return EXIT_OK


def run_command(ns, runner):
    results = runner.run([(ns.command, command_args(ns))])
    report.show(results[0], ns.json)
    return EXIT_OK if results[0].get("ok") else EXIT_FAILED


def _needs_sync_dir(parser, ns):
    """The --project form has to name the folder it will treat as the truth.

    A copy of a project carries the original's cds-sync-folder, and on this
    machine those are absolute paths into the folder the original exports to
    — somebody's git working tree. Left to the property, a headless export
    writes there and a headless import reads from there, neither of which is
    what "verify this copy" meant. The caller knows both paths already, so it
    says which one it means (SPEC 4.2).
    """
    if getattr(ns, "project", None) and not ns.sync_dir:
        parser.error(
            "--project needs --sync-dir. The copy's own cds-sync-folder may "
            "point anywhere, including the folder the original project "
            "exports to, so a headless run says which folder holds its .st "
            "files instead of trusting whatever the copy carried.")


def main(argv=None):
    parser = build_parser()
    ns = parser.parse_args(argv)
    _needs_sync_dir(parser, ns)
    try:
        if ns.command == "installs":
            return run_installs(ns)
        if ns.command == "list":
            return run_list(ns)
        runner = make_runner(ns)
        if getattr(ns, "project", None):
            # First line of the run, before anything has used it.
            report.show_sync_dir(runner.sync_dir(), ns.json)
        if ns.command == "verify":
            return run_verify(ns, runner)
        return run_command(ns, runner)
    except Failure as failure:
        return failure.report()


if __name__ == "__main__":
    sys.exit(main())
