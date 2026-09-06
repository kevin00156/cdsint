# -*- coding: utf-8 -*-
"""
entry_build.py - Trigger build in CODESYS IDE

Compiles the active application and reports errors/warnings.
"""
from __future__ import print_function

import codecs
import os
import time

from engine import build_log
from engine.codesys_constants import kind_of
from engine.codesys_utils import (
    log_warning, safe_str, init_logging, is_debug
)
from engine import entry, settings

# Every severity a build message can carry, ORed into one flags value.
SEVERITY_NAMES = ("FatalError", "Error", "Warning", "Information")


def run_build(app, system, category, severity_enum):
    """Build the application and collect what the IDE said. (messages, seconds).

    Builds a second time when the first said nothing at all, because on
    Delta 1.10 the first build() in a process does not compile: measured on
    one project, three builds in one IDE gave 7.4s and no messages, then
    31.7s with 101 warnings, then 5.8s with the same 101. A headless run only
    ever gets a first build, so without this `cdsint build --project` there
    reports a clean build of code it never compiled — a green light for
    nothing, which is exactly the silent failure SPEC goal 6 rules out.

    "Nothing at all" is the signal rather than a count, because a real build
    always writes at least its own started and completed lines into the
    category; those are asked for (the mask includes Information) and then
    skipped when counting. Twice and no further: if the second is silent too,
    the caller is told that instead of a number.
    """
    started = time.time()
    app.build()
    messages = build_messages(system, category, severity_enum)
    if not messages:
        app.build()
        messages = build_messages(system, category, severity_enum)
    return messages, time.time() - started


def build_messages(system, category, severity_enum):
    """What the IDE has to say about the build, or nothing when it said nothing.

    ScriptEngine 4.0.0.0 — Delta 1.8 and 1.10, Lenze 3.24 — wants two things
    from get_message_objects that this used to give it one of. Both of its
    overloads take a severity mask as well as the category, and the category
    has to be one that is actually holding messages: a build that recompiled
    nothing leaves Build registered but empty, and asking it for messages
    then raises "Value cannot be null. Parameter name: category", which
    turned a clean build into a traceback. Both measured on Delta 1.10;
    4.2.0.0 tolerates each, which is why stock CODESYS never showed either.

    Asking which categories are active first is what separates "the build had
    nothing to say" from "the build could not be read" — and only the first
    of those is safe to report as zero errors.
    """
    if not holds_messages(system, category):
        return []
    return system.get_message_objects(category, every_severity(severity_enum))


def holds_messages(system, category):
    """Is this category one of the ones with something in it right now?"""
    wanted = str(category).lower()
    return any(str(found).lower() == wanted
               for found in system.get_message_categories(True))


def every_severity(severity_enum):
    """The severity mask that means "all of them".

    The members are named rather than a literal mask written out, so a
    ScriptEngine that does not have one of them is a name that is missing
    here, not a count that is silently wrong.
    """
    wanted = None
    for name in SEVERITY_NAMES:
        member = getattr(severity_enum, name, None)
        if member is None:
            continue
        wanted = member if wanted is None else wanted | member
    if wanted is None:
        raise AttributeError(
            "this IDE's Severity has none of %s, so there is no way to ask "
            "for the build's messages" % (", ".join(SEVERITY_NAMES),))
    return wanted


def applications(project):
    """Every Application object in the project, in tree order.

    Counted here, every build, rather than read from a flag the last export
    left in the project. The flag was a cache that went stale in the one
    direction that mattered: the first build after somebody added a second
    application still said "one", so the chooser was skipped, --app did
    nothing and the active application was built instead. A recursive walk
    costs a few hundred reads next to a compile.
    """
    found = []
    for obj in project.get_children(recursive=True):
        if kind_of(safe_str(getattr(obj, "type", ""))) == "application":
            found.append(obj)
    return found


def choose_application(project, system, wanted):
    """Which application to build: (app, refusal). Exactly one of them is None.

    --app names it. Without a name, several applications is a question for a
    person (the stand-in UI turns that into needs_input), and one application
    is not a question at all.
    """
    found = applications(project)
    names = [safe_str(app.get_name()) for app in found]
    if wanted is not None:
        if wanted not in names:
            return None, ("no application called %r in this project; it has %s"
                          % (wanted, ", ".join(names) if names else "none"))
        return found[names.index(wanted)], None
    if not found:
        return None, "Error: No application found to build."
    if len(found) == 1:
        return found[0], None
    chosen = system.ui.choose(
        "Multiple applications detected. Select application to build:", names)
    try:
        index = chosen[0]
    except TypeError:
        # Some versions hand back a bare index, others (index, label).
        index = chosen
    if index is None or index < 0:
        return None, "Build cancelled by user."
    return found[index], None


def _object_text(obj_ref):
    """This object's declaration and implementation, as far as it will say.

    Both halves are read once and handed down: locate_message needs them
    together, and each read crosses into .NET (PRINCIPLES 3).
    """
    decl = ""
    impl = ""
    if obj_ref is None:
        return decl, impl
    try:
        if getattr(obj_ref, "textual_declaration", None):
            decl = safe_str(obj_ref.textual_declaration.text)
        if getattr(obj_ref, "textual_implementation", None):
            impl = safe_str(obj_ref.textual_implementation.text)
    except Exception as exc:
        log_warning("Could not read the text of the object a build message "
                    "points at: " + safe_str(exc))
    return decl, impl


def _attr(msg, name, default):
    """One attribute of a build message, or the default when it will not say.

    getattr with a default does NOT do this. Under IronPython 2.7 a property
    that raises propagates straight out of getattr, while hasattr() swallowed
    it and answered False -- which is exactly why the two looked
    interchangeable and were not. Delta 1.10 answers "The object GUID '...' is
    not valid" for messages about an object the build no longer has, and it
    answers it for whichever attribute you ask about, not only `.object`.

    So every optional attribute of a message goes through here. One that will
    not be read costs its own column, not the whole build's verdict.
    """
    try:
        return getattr(msg, name, default)
    except Exception as exc:
        log_warning("A build message will not say its %s: %s"
                    % (name, safe_str(exc)))
        return default


def _message_id(msg):
    """The 'C0018' the IDE would show, or just the prefix when it has no number."""
    prefix = _attr(msg, "prefix", None)
    prefix = safe_str(prefix) if prefix else ""
    number = _attr(msg, "number", 0)
    if number and number > 0:
        return "%s%04d" % (prefix, number)
    return prefix


def _message_object(msg, app_name):
    """(object column text, the object itself). "N/A" when there is none."""
    obj_ref = _attr(msg, "object", None)
    if not obj_ref:
        return "N/A", None
    try:
        return "{} [{}]".format(safe_str(obj_ref.get_name()), app_name), obj_ref
    except Exception:
        # A message can name an object whose plugin is missing. Its str() is
        # ugly but it is the only handle the reader has left.
        return safe_str(obj_ref), obj_ref


def collect_rows(messages, app_name):
    """(rows, errors, warnings) from the messages one build produced.

    The IDE's own started/completed lines are skipped: they are asked for --
    the severity mask includes Information, which is how run_build tells a
    silent build from a clean one -- but they are not findings.
    """
    rows = []
    errors = 0
    warnings = 0
    for msg in messages:
        try:
            # These two are what makes a message a finding at all, so a
            # message that will not answer them is skipped rather than
            # counted. Everything else goes through _attr and costs at most
            # its own column (SPEC D13).
            text = safe_str(msg.text)
            severity = str(msg.severity)
        except Exception as exc:
            log_warning("Skipping a build message that will not be read: "
                        + safe_str(exc))
            continue
        if "Build started" in text or "Compile complete" in text:
            continue
        if "Error" in severity:
            errors += 1
        if "Warning" in severity:
            warnings += 1

        obj_text, obj_ref = _message_object(msg, app_name)
        decl, impl = _object_text(obj_ref)
        line, col, section = build_log.locate_message(
            text, _attr(msg, "position", -1), decl, impl)
        rows.append(build_log.row("{}: {}".format(_message_id(msg), text),
                                  obj_text, build_log.position_text(line, col,
                                                                    section)))
    return rows, errors, warnings


def _write_build_log(base_dir, app_name, lines):
    """Write build_<app>.log, in debug mode only.

    A normal run leaves the sync folder holding project content and nothing
    else; this file is part of the debug audit trail.
    """
    if not (base_dir and os.path.exists(base_dir) and is_debug()):
        return
    safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_"
                        for c in app_name)
    path = os.path.join(base_dir, "build_{}.log".format(safe_name))
    try:
        with codecs.open(path, "w", "utf-8") as handle:
            handle.write("\n".join(lines))
        print("Build log saved to: " + path)
    except (IOError, OSError) as exc:
        print("Error saving build log: " + safe_str(exc))


def _nothing_was_built(app_name, elapsed):
    """A build that produced no output at all, not even its own summary line.

    Reported as a failure rather than as zero errors: run_build already built
    twice, so this is the IDE saying nothing twice over, and "0 errors" would
    be a green light for code nobody compiled.
    """
    return ("{} built in {:.2f}s and the IDE reported nothing at all, not "
            "even its own summary line, so there is no build result here to "
            "trust".format(app_name, elapsed))


def build_project(base_dir, projects_obj=None):
    """Build the active application, write its log, and report the counts.

    Three steps and nothing else: build, collect what the IDE said, hand back
    a verdict. Working out which line each message points at is
    engine/build_log.py, where it can be tested without an IDE.
    """
    from System import Guid
    # The category CODESYS files build messages under.
    build_category = Guid("97F48D64-A2A3-4856-B640-75C046E37EA9")

    projects_obj = projects_obj or entry.borrowed(globals(), "projects")
    if projects_obj is None or not projects_obj.primary:
        msg = "Error: 'projects' object not found or no project open."
        system.ui.error(msg)
        return entry.result(False, msg)

    app, refused = choose_application(projects_obj.primary, system,
                                      entry.flags(globals()).get("app"))
    if refused:
        system.ui.error(refused)
        return entry.result(False, refused)

    app_name = safe_str(app.get_name())
    print("=== Starting Project Build ===")
    print("Application: " + app_name)

    try:
        system.clear_messages(build_category)
    except Exception as exc:
        # An IDE that will not clear the category still builds; the count is
        # then of this build plus whatever was already filed, which is worth
        # a line rather than a silent skip.
        log_warning("Could not clear the previous build messages: "
                    + safe_str(exc))

    try:
        messages, elapsed = run_build(app, system, build_category, Severity)
        if not messages:
            nothing = _nothing_was_built(app_name, elapsed)
            print(nothing)
            system.ui.error(nothing)
            return entry.result(False, nothing, application=app_name,
                                errors=0, warnings=0)

        rows, errors, warnings = collect_rows(messages, app_name)
        _write_build_log(base_dir, app_name,
                         build_log.table(app_name, rows, errors, warnings))
        return _verdict(app_name, errors, warnings, elapsed)
    except Exception as exc:
        # The traceback goes to stdout, which reaches the caller as
        # stdout_tail. A .NET exception's message on its own can be as
        # useless as "值不能為 null。參數名稱: category" -- true, and no help
        # at all in saying which of these calls said it.
        import traceback
        failure = "Build process failed: " + safe_str(exc)
        print("Build Error: " + safe_str(exc))
        print(traceback.format_exc())
        system.ui.error(failure)
        return entry.result(False, failure)


def _verdict(app_name, errors, warnings, elapsed):
    """Say how it went, on screen and in the result (SPEC D11).

    The errors themselves are not in here: the IDE's message store has them
    with object and line, and cds/ide/messages.py reads them from there. Two
    copies of the same list would drift (SPEC D16).
    """
    body = "{}\nErrors: {}\nWarnings: {}\nTime: {:.2f}s".format(
        app_name, errors, warnings, elapsed)
    print(build_log.summary(errors, warnings)
          + " (Time: {:.2f}s)".format(elapsed))
    if errors == 0:
        system.ui.info(body)
    else:
        system.ui.error(body)

    status = "Build Success" if errors == 0 else "Build Failed"
    return entry.result(errors == 0,
                        "{}: {}, {} errors, {} warnings in {:.2f}s".format(
                            status, app_name, errors, warnings, elapsed),
                        application=app_name, errors=errors, warnings=warnings)


def main():
    # A build does not need the sync folder, so a project that has not chosen
    # one still builds and loses only its debug log. A settings file that
    # cannot be read is the other thing entirely, and it stops the command
    # here (SPEC 4.4).
    values, base_dir, error = settings.prepare(globals())
    if error:
        system.ui.error(error)
        return entry.result(False, error)
    init_logging(base_dir, values["debug"])
    return build_project(base_dir)

if __name__ == "__main__":
    main()
