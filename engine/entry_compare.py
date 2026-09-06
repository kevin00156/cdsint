# -*- coding: utf-8 -*-
"""
entry_compare.py - Compare CODESYS project with disk files

Compares .st and .xml files between the CODESYS IDE and the sync folder to identify:
- Modified objects (content hash mismatch)
- New objects in IDE (not on disk)
- Deleted objects (on disk but not in IDE)
- New files on disk (not in metadata, e.g. from git pull)

Outputs a concise git-style difference list and saves to compare.log.
"""
from __future__ import print_function

import os
import sys
import codecs
import time

from engine.codesys_utils import (
    init_logging, log_info, resolve_projects, is_debug
)
from engine.codesys_compare_engine import find_all_changes
from engine import entry, settings, unhandled



def compare_project(base_dir, values, projects_obj=None):
    """Compare CODESYS project objects with disk files"""
    
    projects_obj = resolve_projects(projects_obj, globals())
    
    if projects_obj is None or not projects_obj.primary:
        msg = "Error: 'projects' object not found or no project open."
        system.ui.error(msg)
        return entry.result(False, msg)

    unhandled.start()
    print("=== Starting Project Comparison ===")
    print("Comparing: CODESYS IDE <-> " + base_dir)
    start_time = time.time()
    
    export_xml = values["export_xml"]
    
    # ── Run comparison engine ──
    print("Comparing IDE objects with disk...")
    results = find_all_changes(base_dir, projects_obj, export_xml=export_xml)
    
    different = results["different"]
    new_in_ide = results["new_in_ide"]
    new_on_disk = results["new_on_disk"]
    moved = results.get("moved", [])
    unchanged_count = results["unchanged_count"]
    # ── Generate report ──
    elapsed = time.time() - start_time
    diff_lines = []
    
    if different:
        for item in different:
            line = "  M  " + item["path"] + "  (" + item["type"] + ")"
            diff_lines.append(line)
    
    if new_in_ide:
        for item in new_in_ide:
            line = "  +  " + item["path"] + "  (" + item["type"] + ")"
            diff_lines.append(line)
    
    # deleted_from_ide is now merged into new_on_disk logic
    
    if new_on_disk:
        for item in new_on_disk:
            line = "  *  " + item["path"] + "  (new on disk)"
            diff_lines.append(line)
    
    if moved:
        for item in moved:
            line = "  ~  " + item["name"] + "  (" + item["type"] + ")  IDE:" + item["ide_path"] + " -> Disk:" + item["disk_path"]
            diff_lines.append(line)
    
    print("")
    if diff_lines:
        print("CHANGES:")
        for line in diff_lines:
            print(line)
    else:
        print("No differences found - IDE and disk are in sync!")
    
    counts = "M:" + str(len(different)) + " +:" + str(len(new_in_ide)) \
             + " *:" + str(len(new_on_disk)) \
             + " ~:" + str(len(moved)) \
             + " =:" + str(unchanged_count) + " | {:.2f}s".format(elapsed)

    print("")
    print("Summary: " + counts)

    log_info("COMPARE: " + counts)
    if diff_lines:
        log_info("DIFF:\n" + "\n".join(diff_lines))

    # ── Show UI ──
    if not diff_lines:
        system.ui.info("IDE and Disk are in sync!\n\nObjects checked: " + str(unchanged_count))

    # Compare only looks, so differences are the answer, not a failure. An
    # object it could not classify is a different matter: it is missing from
    # every one of those counts, which makes the answer wrong rather than
    # inconvenient (SPEC D13).
    missing = unhandled.names()
    return entry.result(not missing,
                        counts if not missing else
                        counts + " -- " + unhandled.summary(),
                        different=len(different), new_in_ide=len(new_in_ide),
                        new_on_disk=len(new_on_disk), moved=len(moved),
                        unchanged=unchanged_count, failed_objects=missing)


def main():
    values, base_dir, error = settings.prepare(globals())
    if error is None and base_dir is None:
        # compare is IDE against disk, so with no folder there is no disk
        # half and nothing to compare against.
        error = settings.folder_missing(globals())
    if error:
        system.ui.warning(error)
        return entry.result(False, error)

    log_file_obj = None
    original_stdout = sys.stdout
    original_stderr = sys.stderr

    if base_dir:
        init_logging(base_dir, values["debug"])

        # compare.log mirrors console output; debug-only so a normal run is clean.
        if is_debug():
            try:
                log_path = os.path.join(base_dir, "compare.log")
                log_file_obj = codecs.open(log_path, "w", "utf-8")

                class Tee(object):
                    def __init__(self, terminal, file_obj):
                        self.terminal = terminal
                        self.file_obj = file_obj
                    def write(self, message):
                        self.terminal.write(message)
                        try:
                            self.file_obj.write(message)
                        except:
                            pass
                    def flush(self):
                        self.terminal.flush()
                        try:
                            self.file_obj.flush()
                        except:
                            pass

                sys.stdout = Tee(original_stdout, log_file_obj)
                sys.stderr = Tee(original_stderr, log_file_obj)
            except Exception as e:
                pass

    try:
        return compare_project(base_dir, values)
    finally:
        if log_file_obj:
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            log_file_obj.close()


if __name__ == "__main__":
    main()
