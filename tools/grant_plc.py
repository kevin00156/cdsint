# -*- coding: utf-8 -*-
"""Set cds-sync-plc on a test copy, so the bench can exercise the PLC commands.

**For copies made for testing, and nothing else.** cds/ide/config.py refuses
to write this property and cdsint has no flag that does, on purpose: the
property means "a person sat in this IDE and decided" (SPEC 6.5), and a tool
that grants it on request would empty it of that meaning.

That policy is a policy, not a wall — headless mode runs arbitrary IronPython
inside the IDE, so anything the IDE can do, a --runscript can do, and this
file is the proof rather than a hole. It exists so a bench run can get past
the gate without a person clicking through Project Information, and it is
kept out of cdsint/ and cds/ so nothing a user installs can reach it.

Point it at a copy. It writes the property and saves, which rewrites the
.project file.

    set CDSINT_GRANT_PROJECT=<a copy of a .project>
    set CDSINT_GRANT_PLC=connect,download
    <exe> --profile="<name>" --noUI --runscript="<abs path to this file>"

A GUI-subsystem exe hands a shell no output, so the outcome also goes to
%TEMP%\\cdsint-work\\grant_plc-<pid>.txt (or CDSINT_GRANT_OUT). The last line
is OK or FAILED.

Environment:
    CDSINT_GRANT_PROJECT   the .project to open (required)
    CDSINT_GRANT_PLC       what to write, e.g. "connect,download" (required)
    CDSINT_GRANT_ANSWERS   IDE prompts to pre-answer, "KEY=VALUE,KEY=VALUE"
    CDSINT_GRANT_OUT       where to write the outcome
"""
from __future__ import print_function

import os
import sys
import traceback

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from cds.core import props  # noqa: E402
from cds.ide import headless, project  # noqa: E402


def report_path():
    override = os.environ.get("CDSINT_GRANT_OUT")
    if override:
        return override
    base = os.path.join(os.environ.get("TEMP", "."), "cdsint-work")
    if not os.path.exists(base):
        os.makedirs(base)
    return os.path.join(base, "grant_plc-%s.txt" % os.getpid())


def answers(raw):
    """"KEY=VALUE,KEY=VALUE" as a mapping, for headless.answer_prompts."""
    found = {}
    for pair in (raw or "").split(","):
        if "=" in pair:
            key, value = pair.split("=", 1)
            found[key.strip()] = value.strip()
    return found


def grant(ide_globals, path, value, said):
    """Open, write the property, save. True when the file on disk has it.

    Read back after the save rather than trusting set_prop, because the two
    failures that matter here — a read-only copy and an IDE that would not
    save — both leave the in-memory value looking fine.
    """
    headless.answer_prompts(ide_globals, answers(
        os.environ.get("CDSINT_GRANT_ANSWERS")))
    opened = headless.open_project(ide_globals, path)
    if opened is None:
        said.append("%s did not open; an unanswered prompt is the usual "
                    "reason, and the keys are above" % path)
        return False
    projects_obj = ide_globals["projects"]
    said.append("opened " + str(getattr(opened, "path", path)))
    said.append("%s was %r" % (props.PLC, project.prop(projects_obj,
                                                       props.PLC)))
    if not project.set_prop(projects_obj, props.PLC, value):
        said.append("could not write %s" % props.PLC)
        return False
    if not project.save(projects_obj):
        said.append("the IDE would not save the project")
        return False
    written = project.prop(projects_obj, props.PLC)
    said.append("%s is now %r" % (props.PLC, written))
    return written == value


def run(ide_globals):
    """The whole job as text, ending in OK or FAILED."""
    path = os.environ.get("CDSINT_GRANT_PROJECT")
    value = os.environ.get("CDSINT_GRANT_PLC")
    said = ["project: %s" % path, "value: %s" % value, ""]
    if not path or not value:
        said.append("set CDSINT_GRANT_PROJECT and CDSINT_GRANT_PLC")
        said.append("FAILED")
        return "\n".join(said)
    try:
        ok = grant(ide_globals, path, value, said)
    except Exception:
        said.append(traceback.format_exc())
        ok = False
    said.append("OK" if ok else "FAILED")
    return "\n".join(said)


def main(ide_globals):
    text = run(ide_globals)
    path = report_path()
    handle = open(path, "wb")
    try:
        handle.write(text.encode("utf-8"))
    finally:
        handle.close()
    print(text)
    print("report: " + path)


if __name__ == "__main__":
    main(globals())
