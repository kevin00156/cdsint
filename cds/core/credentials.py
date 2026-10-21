# -*- coding: utf-8 -*-
"""Where the device login comes from: two environment variables (SPEC D14).

The CLI and the engine both name them, and the CLI may not import engine/,
so the names live here. The CLI copies the pair into the commands whose watcher
has to log in, because a watcher runs in the IDE's process and never sees the
shell's environment.

Pure Python (PRINCIPLES.md 4): no CODESYS imports.
"""
from __future__ import print_function

import os

USER_ENV = "CDS_DEV_USER"
PASS_ENV = "CDS_DEV_PASS"


def from_environment():
    """{"user", "password"} when both variables are set, else None.

    Half a login is no login: a watcher handed a user with no password would
    try it and report a refusal that looks like a wrong password.
    """
    user = os.environ.get(USER_ENV)
    password = os.environ.get(PASS_ENV)
    if not user or not password:
        return None
    return {"user": user, "password": password}
