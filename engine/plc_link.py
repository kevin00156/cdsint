# -*- coding: utf-8 -*-
"""The link to a controller: the login, which device, through which gateway.

Everything between "this project is open" and "there is a connection to talk
over". Credentials come from the environment and nowhere else (SPEC D14),
and the credential dialog is switched off before anything connects -- under
--noUI an unanswerable dialog is not a failure, it is a hang.
"""
from __future__ import print_function

import os

from engine.codesys_utils import log_warning, safe_str
from engine.ide_read import children_of, kind_of, name_of

# The only place either credential is read (D14). Named constants so the
# password's name appears once in the code and the grep for it stays honest.
USER_ENV = "CDS_DEV_USER"
PASS_ENV = "CDS_DEV_PASS"

# What every CODESYS runtime listens on for device connections unless
# somebody moved it. Only used when --gateway was given: without that flag
# nothing here touches the project's own gateway settings.
DEFAULT_DEVICE_PORT = 11740


# --------------------------------------------------------------------------
# Who we log in as
# --------------------------------------------------------------------------

def credentials():
    """The device login, from the environment and nowhere else (D14).

    A report gets committed or pasted into a ticket, and a command line ends
    up in a shell history, so neither may carry these.
    """
    return os.environ.get(USER_ENV, ""), os.environ.get(PASS_ENV, "")


def silence_credential_dialogs(online_api, ide_globals):
    """Switch the dialog off and hand over the environment's login.

    Returns (note, problem); one is None. This is the line that makes the
    whole command unattended: without it a controller that wants a login pops
    a window, and under --noUI that is not a failure anyone can read — it is
    a process that never returns.

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
                      "under --noUI a controller that asks for a login opens "
                      "a window nothing can close, so the connection would "
                      "never return. Nothing was tried.")
    return "; ".join([off, hand_over_credentials(online_api)]), None


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
    return "logging in as %s (from %s and %s)" % (user, USER_ENV, PASS_ENV)


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


def aim_at_gateway(online_api, device_node, address, port):
    """Point the device at `address`. Returns (note, problem); one is None.

    Only called when --gateway was given. The gateway belongs to the IDE
    profile, not to the project, so the same project opened in another
    install can come back "Gateway not configured properly", and this is the
    way past that. Its absence is not a reason to guess one: what the project
    already carries is somebody's answer, and overwriting it would be a
    change to the project made in passing by a read-only command.
    """
    gateways = list(getattr(online_api, "gateways", []) or [])
    if not gateways:
        return None, ("--gateway %s was given but this IDE profile has no "
                      "gateway defined, so there is nothing to reach it "
                      "through" % address)
    gateway = gateways[0]
    try:
        node = gateway.find_address_by_ip(address, port)
        device_node.set_gateway_and_ip_address(gateway, address, port)
    except Exception as exc:
        return None, ("%s:%d could not be reached through gateway %s: %s"
                      % (address, port,
                         safe_str(getattr(gateway, "name", gateway)),
                         safe_str(exc)))
    return ("gateway: %s -> %s:%d (node address %s)"
            % (safe_str(getattr(gateway, "name", gateway)), address, port,
               safe_str(node))), None


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


