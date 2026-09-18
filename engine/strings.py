# -*- coding: utf-8 -*-
"""Three string primitives every layer of the engine leans on.

safe_str() is the one way an IDE value becomes text on both runtimes:
IronPython 2.7 hands back unicode or .NET strings, CPython 3 only str.
calculate_hash() is the CRC that decides whether a .st changed, and
clean_filename() is what an object name has to go through to become a
file name.

Moved out of codesys_utils.py unchanged.
"""
from __future__ import print_function

import zlib
import sys
from engine.codesys_constants import FORBIDDEN_CHARS


def calculate_hash(content):
    """Calculate CRC32 checksum of string content (faster than SHA256)"""
    if content is None:
        return ""
    if isinstance(content, str):
        content = content.encode('utf-8')
    # CRC32 returns signed int, convert to unsigned and format as hex
    crc = zlib.crc32(content) & 0xFFFFFFFF
    return "%08X" % crc


def safe_str(value):
    """Safely convert value to string, handling Unicode in Python 2.7"""
    if value is None:
        return ""
    try:
        if sys.version_info[0] < 3:
            if isinstance(value, unicode):
                return value
            return unicode(value)
        return str(value)
    except:
        return "N/A"


def clean_filename(name):
    """Clean filename from invalid characters"""
    clean_name = name
    for char in FORBIDDEN_CHARS:
        clean_name = clean_name.replace(char, "_")
    return clean_name
