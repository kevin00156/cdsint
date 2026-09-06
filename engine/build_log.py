# -*- coding: utf-8 -*-
"""Where a build message points, and how the build log is laid out.

Pure text in, pure text out. Nothing here touches the IDE, which is the whole
point: working out which line an error is about used to be a hundred lines
buried three levels inside the loop that reads the messages, so the only way
to exercise it was to build a real project on a real IDE and look at the log.

CODESYS gives a message a character offset into the object's text, and the
declaration and implementation are separate texts that the offset runs across
as if they were one. That is the arithmetic in _from_position. It is often
wrong -- the offset can point at whitespace near the problem rather than at it
-- so the search below overrides it whenever it finds the thing the message is
actually complaining about, and a regex over the message text is the last
resort for a message that carries no usable offset at all.
"""
from __future__ import print_function

import re

# Words that stand alone on a declaration line without a colon. A line with
# neither a colon nor one of these, inside a declaration, is executable code
# somebody put in the wrong half -- which is the error worth pointing at even
# when the offset says somewhere else.
DECL_KEYWORDS = frozenset((
    'VAR', 'END_VAR', 'VAR_INPUT', 'VAR_OUTPUT', 'VAR_IN_OUT',
    'VAR_TEMP', 'VAR_GLOBAL', 'VAR_CONFIG', 'VAR_EXTERNAL', 'VAR_STAT',
    'PROGRAM', 'FUNCTION_BLOCK', 'FUNCTION', 'TYPE', 'END_TYPE',
    'STRUCT', 'END_STRUCT', 'PROTECTED', 'INTERNAL'))

DECL = "(Decl)"
IMPL = "(Impl)"

# Column widths of the table in build_*.log. The description is truncated
# rather than padded: a format specifier pads a short string but lets a long
# one overflow, and one overflowing row breaks the alignment of the file.
DESC_WIDTH = 90
OBJ_WIDTH = 40
RULE = "-" * 160


def _line_and_col(text, index):
    """1-based line and column of a character offset into text."""
    before = text[:index].split('\n')
    return len(before), len(before[-1]) + 1


def _from_position(position, decl, impl):
    """The offset CODESYS reported, read as a line and column.

    The offset runs across declaration and implementation as one text, so an
    offset past the end of the declaration is an offset into the
    implementation.
    """
    if position is None or position < 0:
        return None
    if position < len(decl):
        return _line_and_col(decl, position) + (DECL,)
    rel = min(position - len(decl), len(impl))
    return _line_and_col(impl, rel) + (IMPL,)


def _suspects(text):
    """The identifiers a message is complaining about, as it names them."""
    found = re.findall(r"'([^']+)'", text)
    instead = re.search(r"instead of\s+([a-zA-Z0-9_]+)", text)
    if instead:
        found.append(instead.group(1))
    return [item for item in found if item]


def _is_code_in_a_declaration(decl, line_no):
    """A declaration line that is neither a declaration nor a block marker.

    This is somebody's executable statement sitting above END_VAR, and it is
    what the message is about however far the reported offset is from it.

    An assignment slips through, because ":=" contains a colon and the test
    for "this line declares something" is that it has one. Kept as it is:
    this is a hint that improves where an error points, not a rule anything
    depends on, and the offset still answers when it finds nothing.
    """
    lines = decl.split('\n')
    if line_no > len(lines):
        return False
    content = lines[line_no - 1].strip()
    if ":" in content:
        return False
    return not (content in DECL_KEYWORDS
                or any(content.startswith(word) for word in DECL_KEYWORDS))


def _from_text_search(text, position, decl, impl):
    """Find what the message names, and prefer it to the reported offset.

    Two answers, in this order. Code in a declaration wins outright and stops
    the search. Otherwise the occurrence nearest the reported offset wins,
    because a name appearing five times in one POU is five candidates and the
    offset is the only thing that says which.
    """
    at = position if position is not None and position >= 0 else 0
    nearest = None
    least = None
    for suspect in _suspects(text):
        pattern = r"\b" + re.escape(suspect) + r"\b"
        for match in re.finditer(pattern, decl):
            line, col = _line_and_col(decl, match.start())
            if _is_code_in_a_declaration(decl, line):
                return line, col, DECL
            distance = abs(match.start() - at)
            if least is None or distance < least:
                least, nearest = distance, (line, col, DECL)
        for match in re.finditer(pattern, impl):
            line, col = _line_and_col(impl, match.start())
            distance = abs(len(decl) + match.start() - at)
            if least is None or distance < least:
                least, nearest = distance, (line, col, IMPL)
    return nearest


def _from_message_text(text):
    """Some messages carry no offset and say "Line 12, Column 3" instead."""
    line = re.search(r'[Ll]ine[:\s]+(\d+)', text)
    if not line:
        return None
    col = re.search(r'[Cc]olumn[:\s]+(\d+)', text)
    return int(line.group(1)), int(col.group(1)) if col else 0, ""


def locate_message(text, position, decl, impl):
    """Where this build message points: (line, column, section).

    (0, 0, "") when nothing in the message or the object says. The caller
    prints a position only when the line is above zero, so a guess is never
    dressed up as an answer.
    """
    found = _from_text_search(text, position, decl, impl)
    if found is None:
        found = _from_position(position, decl, impl)
    if found is None:
        found = _from_message_text(text)
    return found or (0, 0, "")


def position_text(line, col, section):
    """The position column of one row, empty when there is no position."""
    if line <= 0:
        return ""
    return "Line {}, Col {} {}".format(line, col, section)


def row(description, obj_text, position):
    """One line of the table, with the description cut to fit its column."""
    flat = description.replace('\r', '').replace('\n', ' ')
    if len(flat) > DESC_WIDTH:
        flat = flat[:DESC_WIDTH - 3] + "..."
    return "{:<{dw}} | {:<{ow}} | {}".format(flat, obj_text, position,
                                             dw=DESC_WIDTH, ow=OBJ_WIDTH)


def summary(errors, warnings):
    return "Compile complete -- {} errors, {} warnings".format(errors, warnings)


def table(app_name, rows, errors, warnings):
    """The whole build_*.log: a header, the rows, and the count at the end."""
    head = "{:<{dw}} | {:<{ow}} | {}".format("Description", "Object",
                                             "Position",
                                             dw=DESC_WIDTH, ow=OBJ_WIDTH)
    lines = ["------ Build started: Application: {} ------".format(app_name),
             head, RULE]
    lines.extend(rows)
    lines.append(RULE)
    lines.append(summary(errors, warnings))
    return lines
