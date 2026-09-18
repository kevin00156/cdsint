# -*- coding: utf-8 -*-
"""The .gitignore and .gitattributes an export leaves in the sync folder.

Written once, never overwritten: the folder is under version control by
somebody else after that.

Moved out of codesys_utils.py unchanged.
"""
from __future__ import print_function

import os
import codecs
from engine.strings import safe_str
from engine.sync_log import log_error, log_info


def ensure_git_configs(export_dir):
    """Create .gitignore and .gitattributes if they don't exist in the export directory."""
    gitignore_path = os.path.join(export_dir, ".gitignore")
    gitattributes_path = os.path.join(export_dir, ".gitattributes")
    
    # 1. Gitignore handling
    if not os.path.exists(gitignore_path):
        content = [
            "# CODESYS Sync local files",
            "*.json",
            "*.log",
            "*.tmp",
            "*.bak",
            "",
            "# CODESYS temporary and build files",
            "*.~u",
            "*.precompilecache",
            "*.opt",
            "*.bootinfo",
            "*.bootinfo_guids",
            "*.compileinfo",
            "*.simulation.bootinfo",
            "*.simulation.bootinfo_guids",
            "*.simulation.compileinfo",
            ""
        ]
        try:
            with codecs.open(gitignore_path, "w", "utf-8") as f:
                f.write("\n".join(content))
            log_info("Created: .gitignore")
        except Exception as e:
            log_error("Failed to create .gitignore: " + safe_str(e))
    else:
        # File exists, check if essential patterns are present
        try:
            with codecs.open(gitignore_path, "r", "utf-8") as f:
                lines = f.readlines()
            
            # Ensure *.log is ignored
            if not any("*.log" in line for line in lines):
                with codecs.open(gitignore_path, "a", "utf-8") as f:
                    f.write("\n*.log\n")
                log_info("Updated .gitignore with *.log")
        except: pass

    # 2. Gitattributes handling
    if not os.path.exists(gitattributes_path):
        content = [
            "# Git LFS configuration for CODESYS project binary",
            "*.project filter=lfs diff=lfs merge=lfs -text",
            "",
            "# Prevent line ending conversion for CODESYS Structured Text files",
            "*.st -text",
            "",
            "# GitHub linguist language detection",
            "*.st linguist-language=Pascal",
            ""
        ]
        try:
            with codecs.open(gitattributes_path, "w", "utf-8") as f:
                f.write("\n".join(content))
            log_info("Created: .gitattributes")
        except Exception as e:
            log_error("Failed to create .gitattributes: " + safe_str(e))
