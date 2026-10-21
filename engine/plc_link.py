# -*- coding: utf-8 -*-
"""The link to a controller: the login, which device, through which gateway.

Everything between "this project is open" and "there is a connection to talk
over". Credentials come from the caller's environment and nowhere else (SPEC
D14), and the credential dialog is switched off before anything connects --
an unanswerable dialog is not a failure, it is a hang.
"""
from __future__ import print_function

import os

from cds.core.credentials import PASS_ENV, USER_ENV
from engine.strings import safe_str
from engine.sync_log import log_warning
from engine.ide_read import children_of, kind_of, name_of


# What every CODESYS runtime listens on for device connections unless
# somebody moved it: the port behind --gateway when no --port is given.
DEFAULT_DEVICE_PORT = 11740

# The IDE's words when another client holds the controller (research 3.2).
ALREADY_LOGGED_IN = "already logged in"


# --------------------------------------------------------------------------
# Who we log in as
# --------------------------------------------------------------------------

def credentials():
    """The device login, from the environment and nowhere else (D14).

    The --project form's: its IDE is a child of the caller's shell. A
    report gets committed or pasted into a ticket, and a command line ends
    up in a shell history, so neither may carry these.
    """
    return os.environ.get(USER_ENV, ""), os.environ.get(PASS_ENV, "")


def silence_credential_dialogs(online_api, ide_globals,
                               hand_over=None):
    """Switch the dialog off and hand over the caller's login.

    `hand_over(online_api)` gives the API the login and returns the note
    saying which; by default the environment's (hand_over_credentials), and
    in the watcher only what the command carried (hand_over_forwarded).

    Returns (note, problem); one is None. This is the line that makes the
    whole command unattended: without it a controller that wants a login pops
    a window, and with nobody to answer it that is not a failure anyone can
    read -- it is a call that never returns.

    A problem here stops the trip. It used to print "will hang this run" and
    carry on into exactly that hang, which on the WSL bench cost four runs of
    360 seconds each and told the reader nothing. Not being able to switch
    the dialog off is a reason not to connect, and there is no version of
    this worth trying anyway.
    """
    off = switch_fallback_off(online_api,
                              ide_globals.get("CredentialSourceKind"))
    if off is None:
        return None, ("this IDE's scripting API has no way to switch the "
                      "credential dialog off (neither an auth_fallback_modes "
                      "property nor a set_auth_fallback_modes method), and "
                      "a controller that asks for a login would open a "
                      "window nobody is there to close, so the connection "
                      "would never return. Nothing was tried.")
    hand_over = hand_over or hand_over_credentials
    return "; ".join([off, hand_over(online_api)]), None


def switch_fallback_off(online_api, kinds):
    """Forbid the interactive fallback, whichever spelling this IDE has.

    ScriptEngine 4.2.0.0 (CODESYS 3.5.21.40) exposes auth_fallback_modes as a
    settable property and has no setter method at all — calling one, which is
    what this did for its first year, lands in the except and switches
    nothing off. 4.0.0.0 (Lenze 3.24, Delta 1.10) has not been checked, so
    the old spelling stays as a fallback rather than being deleted.

    The property is read back rather than trusted: the whole bug being fixed
    here is a switch that reported itself set and was not, and an assignment
    that quietly lands on a Python attribute instead of the .NET property
    would be that bug again.

    None when neither spelling worked. Written as getattr(kinds, "None")
    because None is a Python keyword and the enum member really is called
    that; spelled as an attribute access the file would not compile.
    """
    none_of_them = None if kinds is None else getattr(kinds, "None", None)
    if none_of_them is None:
        # Without the enum there is no value to assign, and assigning Python's
        # None would read as success while forbidding nothing.
        return None
    try:
        online_api.auth_fallback_modes = none_of_them
        if online_api.auth_fallback_modes == none_of_them:
            return "credential dialogs off (auth_fallback_modes)"
    except Exception:
        pass
    try:
        online_api.set_auth_fallback_modes(none_of_them)
        return "credential dialogs off (set_auth_fallback_modes)"
    except Exception:
        return None


def hand_over_credentials(online_api):
    """Give the API what the environment holds, and say which it was.

    Both variable names appear when there is no login, because a reader who
    sets only the one named in the message gets the same failure again.
    """
    user, password = credentials()
    if not user:
        return ("no %s in the environment, so the controller gets no "
                "credentials; set %s and %s to log in"
                % (USER_ENV, USER_ENV, PASS_ENV))
    online_api.set_default_credentials(user, password)
    return handed_over(user)


def handed_over(user):
    """The note for credentials given to the API, the user named and the
    password never. It says what was done, not "logging in": a run, a stop,
    a logout or a device connection hands them over too and logs in to
    nothing."""
    return "credentials for %s handed over (from %s and %s)" % (
        user, USER_ENV, PASS_ENV)


def hand_over_forwarded(online_api, given):
    """Give the API the login the watcher command carried, and say so.

    Only that: the IDE process's own environment is not the caller's
    (design R4).
    """
    online_api.set_default_credentials(given["user"], given["password"])
    return handed_over(given["user"])


def hand_over_for(trip):
    """The dialog switch and the login the trip's command carried, right
    before one of its online calls. None, or why the call must not be made.

    Every call, not once: held credentials went stale across a runtime
    restart and a project reopen, and the dialog came back (17.5). The note
    is the same every time, so it is said once.

    A command without both is refused before its first online call. The CLI
    never sends one (cdsint/refusals.py), so this is a hand-written command
    file: run on, it would ride on whatever the IDE held from before, or
    stop on the logon dialog.
    """
    given = trip.args.get("credentials")
    if not given or not given.get("user") or not given.get("password"):
        return ("this command carried no device login (%s and %s, both set, "
                "are what the CLI forwards), and an IDE without valid "
                "credentials can stop on its Device User Logon dialog, so "
                "nothing was sent to the controller" % (USER_ENV, PASS_ENV))
    note, problem = silence_credential_dialogs(
        trip.online, trip.globals,
        lambda online: hand_over_forwarded(online, given))
    if problem:
        return problem
    if note not in trip.notes:
        trip.note(note)
    return None


def login_refusal(said):
    """What to tell the caller when login() raised `said`, on one line."""
    if ALREADY_LOGGED_IN in said.lower():
        return ("another client is logged in to the controller and it takes "
                "only one, so downloading would not help: log that client "
                "out and run again. The IDE said: " + said)
    return "the login was refused: " + said


# --------------------------------------------------------------------------
# Which controller, reached how
# --------------------------------------------------------------------------

def find_device(project):
    """The one device node to talk to. Returns (node, problem); one is None.

    Refuses rather than picks when a project has several: which controller to
    download to is not a question with a safe default, and there is no flag
    to answer it with, so the honest answer is to name them and stop (D7).
    """
    devices = []
    for child in children_of(project):
        if kind_of(child) == "device":
            devices.append(child)
    if not devices:
        return None, ("no device node in this project, so there is no "
                      "controller to talk to")
    if len(devices) > 1:
        return None, ("this project has %d device nodes (%s) and there is no "
                      "flag that says which one to use, so nothing was done"
                      % (len(devices), ", ".join(name_of(d)
                                                 for d in devices)))
    return devices[0], None


def gateway_name(gateway):
    return safe_str(getattr(gateway, "name", gateway))


def node_address(device_node, gateways):
    """Where the device node points, as text for a report, or None.

    The node address and the gateway it is reached through, as the node
    holds them (research 17.6). The address is shown as the IDE gives it:
    its last words looked like port and IPv4 on two TCP routes, which is
    not enough to decode it by.
    """
    try:
        address = safe_str(device_node.get_address())
        guid = device_node.get_gateway()
    except Exception:
        return None
    named = [g for g in gateways if getattr(g, "guid", None) == guid]
    if not named:
        return "%s through gateway %s" % (address, safe_str(guid))
    return "%s through %s%s" % (address, gateway_name(named[0]),
                                _host_port(named[0]))


def _host_port(gateway):
    """" at host:port" from a gateway's config_params ({0: host, 1: port})."""
    try:
        params = gateway.config_params
        return " at %s:%s" % (safe_str(params[0]), safe_str(params[1]))
    except Exception:
        return ""


def pick_gateway(gateways, name, address):
    """The profile's gateway to reach `address` through. (gateway, problem).

    A name that was given is the only answer, even when the profile has one
    gateway: a flag that is quietly overruled is a skip wearing another hat.
    Without one, a lone gateway is the only one there is, and of several the
    first listed is not a choice anybody made -- the same address behind
    another gateway can be another controller (D7).
    """
    if not gateways:
        return None, ("--gateway %s was given but this IDE profile has no "
                      "gateway defined, so there is nothing to reach it "
                      "through" % address)
    names = [gateway_name(g) for g in gateways]
    if name is not None:
        if name not in names:
            return None, ("this IDE profile has no gateway called %s (it has "
                          "%s), so nothing was done"
                          % (name, ", ".join(names)))
        return gateways[names.index(name)], None
    if len(gateways) > 1:
        return None, ("this IDE profile has %d gateways (%s) and none was "
                      "named, so nothing was done; pass --gateway-name with "
                      "the one that reaches %s"
                      % (len(gateways), ", ".join(names), address))
    return gateways[0], None


def aim_at_gateway(device_node, gateway, address, port):
    """Point the device at `address`. Returns (note, problem); one is None.

    Every plc command calls it: the address the project carries was found
    by device name, which can reach the wrong controller (SPEC 6.6). The
    gateway belongs to the IDE profile, not to the project, so the same
    project opened in another install can come back "Gateway not configured
    properly", and naming it is also the way past that.
    """
    try:
        node = gateway.find_address_by_ip(address, port)
        device_node.set_gateway_and_ip_address(gateway, address, port)
    except Exception as exc:
        return None, ("%s:%d could not be reached through gateway %s: %s"
                      % (address, port, gateway_name(gateway),
                         safe_str(exc)))
    return ("gateway: %s -> %s:%d (node address %s)"
            % (gateway_name(gateway), address, port, safe_str(node))), None


def names_in(device, directory):
    """The names in one controller directory. What the listing raised is
    let out: a directory that is not there and a link that dropped raise
    alike, so only a listing that worked can say what is absent."""
    items = device.get_file_list_of_directory(directory)
    return [safe_str(item.name) for item in items]


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


# --------------------------------------------------------------------------
# Leaving it as we found it
# --------------------------------------------------------------------------

def logout(session):
    """Leave the controller as we found it, whatever happened in between."""
    try:
        session.logout()
    except Exception as exc:
        log_warning("plc: could not log out cleanly: " + safe_str(exc))


def disconnect(device):
    """A device connection left open stays open for the rest of the run."""
    if device is None:
        return
    try:
        device.disconnect()
    except Exception as exc:
        log_warning("plc: could not disconnect cleanly: " + safe_str(exc))


