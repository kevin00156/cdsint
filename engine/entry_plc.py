# -*- coding: utf-8 -*-
"""plc connect and plc download: what the controller runs, and putting it there.

Both commands end in the same question, and it is the only one worth asking:
**is the machine running this tree?** The compiler answers it. Building the
boot application offline produces a `.crc` beside the `.app`, the controller
keeps the same file at PlcLogic/Application/Application.crc, and bytes 5 to 8
of the two are the identity to compare. `connect` asks the question;
`download` makes the answer true first and then asks it anyway, because a
download that reports success without being read back is a claim, not a
check.

Two gates stand in front of both, and neither is here (SPEC D8, 6.5): the
project property cds-sync-plc says whether this project allows the action at
all (cds/ide/permit.py), and -y says the caller means this call. By the time
a function in this file runs, both have been passed.

Credentials come from the environment and nowhere else (D14), and the
credential dialog is switched off before anything connects — under --noUI an
unanswerable dialog is not a failure, it is a hang.

Only the headless form reaches this file, so it has no menu stub and its
flags arrive as `command_args` rather than as answers to dialogs
(cds/ide/silent.py). The exception is the download confirmation, which is a
question a person would have been asked and so goes through the same
ask_yes_no the import confirmation does.
"""
from __future__ import print_function

import os
import tempfile

from engine import entry, unhandled
from engine.codesys_constants import kind_of
from engine.codesys_online import resolve_online
from engine.codesys_utils import log_warning, resolve_projects, safe_str

# The flags this run was given, put here by cds/ide/silent.py once this
# module's own code has run (silent.ARGS_GLOBAL). Defined so that importing
# the module directly — a test, a REPL — reads "no flags" instead of raising.
command_args = {}

# The only place either credential is read (D14). Named constants so the
# password's name appears once in the code and the grep for it stays honest.
USER_ENV = "CDS_DEV_USER"
PASS_ENV = "CDS_DEV_PASS"

# What every CODESYS runtime listens on for device connections unless
# somebody moved it. Only used when --gateway was given: without that flag
# nothing here touches the project's own gateway settings.
DEFAULT_DEVICE_PORT = 11740

# The verdict, and what it is called in the report (SPEC 6.6).
MATCH = "MATCH"
DIFFERENT = "DIFFERENT"
UNKNOWN = "UNKNOWN"

# Bytes 5 to 8 of a .crc file are the identity; the first four are a header.
# The test for that split is that those four bytes are identical in files
# built from two different projects.
CRC_FIELD = (4, 8)

REMOTE_APP_DIR = "PlcLogic/Application"
REMOTE_CRC = REMOTE_APP_DIR + "/Application.crc"

# The boot application is always written under the same name, so each run
# overwrites the last one rather than leaving a pile nobody reads, and no
# code here ever deletes a directory it did not create.
BOOT_NAME = "cdsint.app"
BOOT_CRC_NAME = "cdsint.crc"
PLC_CRC_NAME = "plc_Application.crc"
SOURCE_ARCHIVE_NAME = "plc_source.projectarchive"

DOWNLOAD_QUESTION = (
    "This will download the whole application to the controller: stop what "
    "is running, write the program, write the boot application so it "
    "survives a power cycle, and start it again. Online change is switched "
    "off, so the running state is lost and every init runs from the "
    "beginning.\n\nProceed?")


# --------------------------------------------------------------------------
# The two commands
# --------------------------------------------------------------------------

def connect():
    """Read the controller and compare what it holds against this project.

    Nothing here writes to the controller: the device-level connection
    (IScriptOnlineDevice) can list and fetch files, which is the whole of
    what this needs, whereas an application login downloads code.
    """
    unhandled.start()
    trip = Trip("connect")
    problem = trip.reach_the_device()
    if problem:
        return trip.failed(problem)
    return trip.read_back()


def download():
    """Put this project on the controller, then read it back and check.

    The confirmation is first, before anything is resolved or connected, so
    a run without -y costs nothing and touches nothing.
    """
    unhandled.start()
    cancelled = confirm()
    if cancelled:
        return entry.result(False, cancelled, action="download", crc=UNKNOWN)
    trip = Trip("download")
    problem = trip.reach_the_device()
    if problem:
        return trip.failed(problem)
    problem = trip.send()
    if problem:
        return trip.failed(problem)
    return trip.read_back()


def confirm():
    """Ask the question -y answers. Returns the refusal text, or None.

    Routed through the engine's own dialog rather than reading the flag here
    because that is what makes it the same -y as import's: cds/ide/silent.py
    holds one table of dialog titles and the argument that answers each, and
    a flag read directly would not be in it (SPEC 4.2). With no -y at all
    that stand-in raises NeedsInput and this never returns; an explicit "no"
    is the case handled here.
    """
    from engine.codesys_ui import ask_yes_no
    if ask_yes_no("Confirm PLC Download", DOWNLOAD_QUESTION):
        return None
    return "PLC download cancelled: not confirmed."


# --------------------------------------------------------------------------
# One trip to the controller
# --------------------------------------------------------------------------

class Trip(object):
    """One plc command: the objects it needs, and what it found out.

    Held together rather than passed around because every step after the
    first needs most of what the ones before it resolved, and a chain of
    six-argument calls hides which step is the one that failed.
    """

    def __init__(self, action, ide_globals=None):
        self.action = action
        self.globals = ide_globals if ide_globals is not None else globals()
        self.args = command_args or {}
        self.projects = None
        self.online = None
        self.device_node = None     # the device in the project tree
        self.device = None          # the live connection to it
        self.notes = []             # what a reader needs to reproduce this
        self._workspace = None      # made only once something is written there
        self.found = {"crc": UNKNOWN, "local_crc": None, "plc_crc": None,
                      "plc_files": [], "source_archive": None}

    # -- getting there ------------------------------------------------------

    def reach_the_device(self):
        """Resolve everything a controller conversation needs. None if ready."""
        self.projects = resolve_projects(None, self.globals)
        if self.projects is None or not getattr(self.projects, "primary", None):
            return "no project is open, so there is no device to talk to"
        self.online = resolve_online(self.globals)
        if self.online is None:
            return ("the CODESYS 'online' API is not reachable from this "
                    "script run, so nothing can connect to a controller")
        self.notes.append(silence_credential_dialogs(self.online, self.globals))
        self.device_node, problem = find_device(self.projects.primary)
        if problem:
            return problem
        return self.point_at_gateway()

    def point_at_gateway(self):
        """Aim the device at --gateway, or leave the project's own settings.

        The gateway belongs to the IDE profile, not to the project, so the
        same project opened in another install can come back "Gateway not
        configured properly". --gateway is the way past that, and its absence
        is not a reason to guess one: what the project already carries is
        somebody's answer, and overwriting it would be a change to the
        project made in passing by a read-only command.
        """
        address = self.args.get("gateway")
        if not address:
            self.notes.append("gateway: whatever the project already holds")
            return None
        port = int(self.args.get("port") or DEFAULT_DEVICE_PORT)
        gateways = list(getattr(self.online, "gateways", []) or [])
        if not gateways:
            return ("--gateway %s was given but this IDE profile has no "
                    "gateway defined, so there is nothing to reach it "
                    "through" % address)
        gateway = gateways[0]
        try:
            node = gateway.find_address_by_ip(address, port)
            self.device_node.set_gateway_and_ip_address(gateway, address, port)
        except Exception as exc:
            return ("%s:%d could not be reached through gateway %s: %s"
                    % (address, port,
                       safe_str(getattr(gateway, "name", gateway)),
                       safe_str(exc)))
        self.notes.append("gateway: %s -> %s:%d (node address %s)"
                          % (safe_str(getattr(gateway, "name", gateway)),
                             address, port, safe_str(node)))
        return None

    # -- the destructive half ----------------------------------------------

    def send(self):
        """Full download, boot application, start. None when it worked.

        OnlineChangeOption.Never is not a preference: an online change keeps
        the running state, and the whole point of a download from a pipeline
        is that every initialisation runs again. The second argument is
        delete_foreign_apps, and False is deliberate — removing applications
        that belong to somebody else is not part of "put this one on".

        create_boot_application() with no argument writes it *on the
        controller*, which is a different call from the one that writes a
        boot application to a local path. Without it the download only lands
        in RAM and PlcLogic/Application/Application.crc still holds the
        previous program, so the check afterwards would compare against the
        wrong thing and pass or fail for the wrong reason.
        """
        application = getattr(self.projects.primary, "active_application", None)
        if application is None:
            return "this project has no active application to download"
        option = self.globals.get("OnlineChangeOption")
        if option is None:
            return ("this IDE did not provide OnlineChangeOption, so a full "
                    "download cannot be asked for explicitly")
        session = self.online.create_online_application(application)
        try:
            session.login(option.Never, False)
            session.create_boot_application()
            session.start()
        except Exception as exc:
            # Named rather than let out as a traceback: "the controller
            # refused the login" and "the download stopped halfway" are
            # things that happen on a bench, not bugs in this file.
            return "the download did not complete: " + safe_str(exc)
        finally:
            _logout(session)
        self.notes.append("download: application state %s"
                          % safe_str(getattr(session, "application_state",
                                             "unknown")))
        return None

    # -- reading it back ----------------------------------------------------

    def read_back(self):
        """Connect, fetch what the controller holds, compare, report.

        Everything the controller can refuse is caught and named here. A
        traceback out of a bench command says "cdsint is broken" when what
        happened is that the machine was off.
        """
        try:
            self.device = self.online.create_online_device(self.device_node)
        except Exception as exc:
            return self.failed("could not open a connection to %s: %s"
                               % (_name(self.device_node), safe_str(exc)))
        try:
            try:
                self.device.connect()
            except Exception as exc:
                return self.failed("%s did not answer: %s"
                                   % (_name(self.device_node), safe_str(exc)))
            self.found["plc_files"] = list_remote(self.device, REMOTE_APP_DIR)
            self.found["plc_crc"] = self.pull_plc_crc()
            self.found["local_crc"] = self.build_boot_application()
            self.found["crc"] = compare_crc(self.found["local_crc"],
                                            self.found["plc_crc"])
            self.found["source_archive"] = self.pull_source_archive()
        finally:
            _disconnect(self.device)
        return self.verdict()

    def pull_plc_crc(self):
        """The controller's own Application.crc, as hex, or None.

        Absent is an answer, not an error: a controller with nothing loaded
        has no such file. It still fails the command, because "cannot tell"
        must not read the same as "matches".
        """
        local = _forget(os.path.join(self.workspace(), PLC_CRC_NAME))
        try:
            self.device.upload_file(REMOTE_CRC, local, True)
        except Exception as exc:
            self.notes.append("%s could not be fetched: %s"
                              % (REMOTE_CRC, safe_str(exc)))
            return None
        return crc_field(read_bytes(local))

    def build_boot_application(self):
        """The boot application this project compiles to, as hex, or None.

        Built from the offline application, which writes the .app and its
        .crc to the path given — the argument is what separates this from
        the call that writes one to the controller.
        """
        application = getattr(self.projects.primary, "active_application", None)
        if application is None:
            self.notes.append("this project has no active application, so "
                              "there is nothing to compare the controller "
                              "against")
            return None
        target = _forget(os.path.join(self.workspace(), BOOT_NAME))
        crc_path = _forget(os.path.join(self.workspace(), BOOT_CRC_NAME))
        try:
            application.create_boot_application(target)
        except Exception as exc:
            self.notes.append("the boot application could not be built: "
                              + safe_str(exc))
            return None
        return crc_field(read_bytes(crc_path))

    def pull_source_archive(self):
        """The source archive the controller holds, when it holds one.

        Only machines that had a source download have it. Nothing here needs
        it, but a run that can retrieve the source behind the CRC it just
        compared has proved the whole claim without writing a byte, so it is
        worth the one call and the path is reported.
        """
        target = _forget(os.path.join(self.workspace(), SOURCE_ARCHIVE_NAME))
        try:
            self.device.upload_source(target)
        except Exception as exc:
            self.notes.append("no source archive on the controller: "
                              + safe_str(exc))
            return None
        return target if os.path.isfile(target) else None

    # -- what came of it ----------------------------------------------------

    def verdict(self):
        """The result record, with the CRC comparison as its gate (SPEC 6.6).

        DIFFERENT and UNKNOWN both fail. compare gets to report differences
        and still be ok because verify is there to turn its counts into a
        verdict; nothing wraps these two commands, so the exit code has to be
        the verdict, and a caller that reads only the exit code is exactly
        the caller SPEC 6.6 has in mind.
        """
        verdict = self.found["crc"]
        if verdict == MATCH:
            summary = ("%s: the controller is running this project (CRC %s)"
                       % (self.action, self.found["plc_crc"]))
        elif verdict == DIFFERENT:
            summary = ("%s: the controller is NOT running this project. Its "
                       "CRC is %s and this project builds to %s"
                       % (self.action, self.found["plc_crc"],
                          self.found["local_crc"]))
        else:
            summary = ("%s: the controller and this project could not be "
                       "compared. %s" % (self.action, self.why_unknown()))
        return self.result(verdict == MATCH, summary)

    def why_unknown(self):
        """Which half of the comparison is missing. Both is a real case."""
        missing = []
        if not self.found["local_crc"]:
            missing.append("this project produced no boot application CRC")
        if not self.found["plc_crc"]:
            missing.append("the controller has no %s" % REMOTE_CRC)
        return "; ".join(missing) or "no reason was recorded, which is a bug"

    def failed(self, problem):
        """A trip that never got as far as a comparison."""
        return self.result(False, "%s: %s" % (self.action, problem))

    def result(self, ok, summary):
        for note in self.notes:
            print("plc %s: %s" % (self.action, note))
        return entry.result(
            ok, summary, action=self.action, notes=list(self.notes),
            workspace=self._workspace, failed_objects=unhandled.names(),
            **self.found)

    def workspace(self):
        """Where this run's .app, .crc and archive go.

        Named after the project rather than made fresh each time, so a second
        run overwrites the first instead of leaving a numbered trail in TEMP,
        and so the path in the report is one a reader can go and look at.
        Made on first use, so a trip that failed before it had anything to
        write leaves no empty directory behind and reports no path.
        """
        if self._workspace is None:
            self._workspace = os.path.join(
                tempfile.gettempdir(), "cdsint", "plc",
                _safe_name(_project_stem(self.projects)))
            if not os.path.isdir(self._workspace):
                os.makedirs(self._workspace)
        return self._workspace


# --------------------------------------------------------------------------
# The pieces that do not need a controller
# --------------------------------------------------------------------------

def credentials():
    """The device login, from the environment and nowhere else (D14).

    A report gets committed or pasted into a ticket, and a command line ends
    up in a shell history, so neither may carry these.
    """
    return os.environ.get(USER_ENV, ""), os.environ.get(PASS_ENV, "")


def silence_credential_dialogs(online_api, ide_globals):
    """Switch the credential dialog off and hand over what the environment has.

    This is the line that makes the whole command unattended. Without it a
    controller that wants a login pops a window, and under --noUI that is not
    a failure anyone can read — it is a process that never returns. Told not
    to fall back to a dialog, the same situation raises where it happens.

    Written as getattr(kinds, "None") because None is a Python keyword and
    the attribute really is called that; spelled as an attribute access the
    file would not compile.
    """
    said = []
    kinds = ide_globals.get("CredentialSourceKind")
    try:
        online_api.set_auth_fallback_modes(getattr(kinds, "None"))
        said.append("credential dialogs off")
    except Exception as exc:
        said.append("credential dialogs could NOT be switched off (%s), so a "
                    "controller that asks for a login will hang this run"
                    % safe_str(exc))
    user, password = credentials()
    if user:
        online_api.set_default_credentials(user, password)
        said.append("logging in as %s (from %s)" % (user, USER_ENV))
    else:
        said.append("no %s in the environment, so the controller gets no "
                    "credentials" % USER_ENV)
    return "; ".join(said)


def find_device(project):
    """The one device node to talk to. Returns (node, problem); one is None.

    Refuses rather than picks when a project has several: which controller to
    download to is not a question with a safe default, and there is no flag
    to answer it with, so the honest answer is to name them and stop (D7).
    """
    devices = []
    for child in _children(project):
        if _kind_of(child) == "device":
            devices.append(child)
    if not devices:
        return None, ("no device node in this project, so there is no "
                      "controller to talk to")
    if len(devices) > 1:
        return None, ("this project has %d device nodes (%s) and there is no "
                      "flag that says which one to use, so nothing was done"
                      % (len(devices), ", ".join(_name(d) for d in devices)))
    return devices[0], None


def list_remote(device, directory):
    """What the controller holds in one directory, as "name size" strings.

    IScriptDirectoryInfo has no get_name(), so the generic name reader prints
    object addresses here — a list that looks full and names nothing.
    """
    try:
        items = device.get_file_list_of_directory(directory)
    except Exception as exc:
        return ["<%s could not be listed: %s>" % (directory, safe_str(exc))]
    listed = []
    for item in items:
        try:
            listed.append("%s%s %s B" % (safe_str(item.name),
                                         "/" if item.is_directory else "",
                                         item.size))
        except Exception as exc:
            listed.append("<an entry that would not describe itself: %s>"
                          % safe_str(exc))
    return listed


def read_bytes(path):
    """The whole of a file, or None when it is not there."""
    if not os.path.isfile(path):
        return None
    handle = open(path, "rb")
    try:
        return handle.read()
    finally:
        handle.close()


def crc_field(raw):
    """The identity bytes of a .crc file as hex, or None if there are none.

    A file too short to hold the field is not a CRC of anything, so it reads
    as "no answer" rather than as a shorter answer that would then compare
    equal to another truncated file.
    """
    start, end = CRC_FIELD
    if raw is None or len(raw) < end:
        return None
    return "".join("%02X" % _byte(value) for value in raw[start:end])


def compare_crc(local, plc):
    """MATCH, DIFFERENT, or UNKNOWN when either side is missing.

    UNKNOWN is not a third shade of the same answer, it is the absence of
    one, and it is kept apart from DIFFERENT because the two call for
    different things: DIFFERENT means download, UNKNOWN means find out why
    there was nothing to compare.
    """
    if not local or not plc:
        return UNKNOWN
    return MATCH if local == plc else DIFFERENT


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def _forget(path):
    """Remove the file this run is about to write, and hand back the path.

    The workspace is named after the project so that runs overwrite each
    other rather than pile up, and that is exactly what makes a stale file
    dangerous: a call that returns without writing would otherwise be read
    as last week's answer to this week's question.
    """
    try:
        if os.path.isfile(path):
            os.remove(path)
    except (IOError, OSError) as exc:
        log_warning("plc: could not clear %s before writing it: %s"
                    % (path, safe_str(exc)))
    return path


def _byte(value):
    """One byte as an int, whether iterating gave us an int or a character."""
    return value if isinstance(value, int) else ord(value)


def _logout(session):
    """Leave the controller as we found it, whatever happened in between."""
    try:
        session.logout()
    except Exception as exc:
        log_warning("plc: could not log out cleanly: " + safe_str(exc))


def _disconnect(device):
    """A device connection left open stays open for the rest of the run."""
    if device is None:
        return
    try:
        device.disconnect()
    except Exception as exc:
        log_warning("plc: could not disconnect cleanly: " + safe_str(exc))


def _children(node):
    try:
        return node.get_children()
    except Exception as exc:
        unhandled.note(node, exc)
        return []


def _kind_of(obj):
    """The profile kind of an object, or None when it will not say (D13)."""
    try:
        return kind_of(safe_str(obj.type))
    except Exception as exc:
        unhandled.note(obj, exc)
        return None


def _name(obj):
    try:
        return safe_str(obj.get_name())
    except Exception:
        return "<an object that will not say its name>"


def _project_stem(projects_obj):
    path = getattr(getattr(projects_obj, "primary", None), "path", None)
    if not path:
        return "unsaved"
    return os.path.splitext(os.path.basename(safe_str(path)))[0]


def _safe_name(stem):
    """A directory name from a project name: these have spaces and Chinese."""
    kept = [c if (c.isalnum() or c in "._-") else "_" for c in stem]
    return "".join(kept) or "unsaved"
