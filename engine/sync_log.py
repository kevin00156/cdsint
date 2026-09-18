# -*- coding: utf-8 -*-
"""The run's log, the debug flag, the interaction timer.

One Logger per run, told by init_logging() what the settings file decided;
log_info/log_warning/log_error print to the IDE console and, in debug,
to a file. The timer keeps a person's time at a prompt out of the sync
timings; save_sync_metadata() is the debug dump.

Moved out of codesys_utils.py unchanged.
"""
from __future__ import print_function

import os
import codecs
import json
import traceback
import time
import tempfile
from engine.strings import safe_str


# --- Logging System ---
# --- Logging System ---
class Logger:
    def __init__(self):
        self.log_file = None
        self.is_final = False
        self.debug = False  # Set by init_logging from the settings file.
        
    def _initialize(self, base_dir=None):
        # If explicitly providing base_dir, override everything
        if base_dir:
            self.log_file = os.path.join(base_dir, "sync_debug.log")
            self.is_final = True
            return

        # If we already have a final path, don't change it unless forced
        if self.is_final:
            return

        # Nothing is looked up here: init_logging() is handed the folder the
        # settings resolved to, and every entry body calls it before anything
        # worth logging happens. TEMP is where a log written before that call
        # goes, and it stays overwritable so the real path still wins.
        if not self.log_file:
            try:
                # Use temp directory to avoid cluttering ScriptDir
                self.log_file = os.path.join(tempfile.gettempdir(), "cds_sync_debug.log")
            except:
                pass
            # allow overwriting later since this is a fallback
            self.is_final = False

    def log(self, level, message, include_traceback=False):
        self._initialize()
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_entry = "[%s] [%s] %s\n" % (timestamp, level, message)
        
        if include_traceback:
            log_entry += traceback.format_exc() + "\n"
            
        print("[%s] %s" % (level, message))

        # Console always shows the message; the log FILE is debug-only so a
        # normal run leaves no sync_debug.log behind. ERROR always writes so a
        # real failure is never silent.
        if not self.debug and level != "ERROR":
            return

        try:
            with codecs.open(self.log_file, "a", "utf-8") as f:
                f.write(log_entry)
        except:
            pass


_logger = Logger()


def log_info(message):
    _logger.log("INFO", message)


def log_warning(message):
    _logger.log("WARNING", message)


def init_logging(base_dir, debug=False):
    """Point the log at the sync folder, and say whether to write one at all.

    Both come from the settings this run read (engine/settings.py), and both
    are handed in: fetching the debug flag here would have the logger reach
    back into the project through two more modules for an answer its caller
    is already holding.
    """
    if base_dir and os.path.exists(base_dir):
        _logger._initialize(base_dir)
    _logger.debug = bool(debug)


def log_error(message):
    _logger.log("ERROR", message, include_traceback=True)


def is_debug():
    """True when the settings file turned debug on (SPEC 4.4).

    The flag reaches here through init_logging(), which every entry body
    calls once with the settings this run read. read_ide_attrs() consults it
    once per object, so reading it off the project would cross into .NET that
    often and need a cache of its own in front of it; a value handed in is
    cheap without one.
    """
    return _logger.debug


# --- Interaction timing -------------------------------------------------
# Sync operations time themselves to report "Time elapsed", but the timed
# region spans blocking dialogs (the orphan-cleanup prompt, the import
# confirmation). Those measure how long a human took to click, which is not
# information about the sync, and it swamped the numbers being compared when
# tuning performance. Prompts routed through timed_prompt() are subtracted.
_interaction_seconds = [0.0]


def reset_interaction_timer():
    """Zero the accumulated prompt time. Call when starting a timed operation."""
    _interaction_seconds[0] = 0.0


def get_interaction_seconds():
    """Seconds spent waiting on user prompts since the last reset."""
    return _interaction_seconds[0]


def timed_prompt(prompt_func, *args, **kwargs):
    """Call a blocking UI prompt, keeping its duration out of sync timings.

    Wrapping at the call site rather than inside codesys_ui keeps this module
    free of the WinForms/clr import that codesys_ui needs.
    """
    started = time.time()
    try:
        return prompt_func(*args, **kwargs)
    finally:
        _interaction_seconds[0] += time.time() - started


def format_elapsed(total_seconds, interaction_seconds=None):
    """Render an elapsed time, noting prompt time when it was material."""
    if interaction_seconds is None:
        interaction_seconds = get_interaction_seconds()
    text = "{:.2f} seconds".format(total_seconds)
    if interaction_seconds >= 0.5:
        text += " (plus {:.2f}s waiting for input)".format(interaction_seconds)
    return text


def save_sync_metadata(base_dir, action, stats, elapsed):
    """Write sync_metadata.json, in debug mode only.

    Used by both entry_export.py and entry_import.py. Part of the debug
    audit trail: a normal run leaves the sync folder holding project content
    and nothing else. The version property is not written here -- it has to be in
    the project before the save, and this runs after it; see
    engine/backup.py's finalize_sync_operation.

    Args:
        base_dir: Export/import directory path
        action: "export" or "import"
        stats: Statistics dict
        elapsed: Elapsed time in seconds (float)
    """
    from engine.codesys_constants import SCRIPT_VERSION
    if not is_debug():
        return

    metadata = {
        "script_version": SCRIPT_VERSION,
        "last_action": action,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "duration_sec": round(elapsed, 2),
        "statistics": stats
    }
    metadata_path = os.path.join(base_dir, "sync_metadata.json")
    try:
        with codecs.open(metadata_path, "w", "utf-8") as f:
            json.dump(metadata, f, indent=2)
        log_info("%s metadata saved to sync_metadata.json (v%s)" % (action.capitalize(), SCRIPT_VERSION))
    except Exception as e:
        log_warning("Failed to save %s metadata: %s" % (action, safe_str(e)))
