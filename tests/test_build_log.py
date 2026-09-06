# -*- coding: utf-8 -*-
"""Where a build message points, worked out without an IDE.

This used to be a hundred lines three levels deep inside the loop that reads
the IDE's messages, so the only way to try it was to build a real project on
a real IDE and read the log afterwards. Everything here is text in, text out.
"""
import pytest

from engine import build_log


DECL = ("FUNCTION_BLOCK MC_Main\n"
        "VAR\n"
        "    iCount : INT;\n"
        "END_VAR\n")
IMPL = ("iCount := iCount + 1;\n"
        "IF iCount > 10 THEN\n"
        "    iCount := 0;\n"
        "END_IF\n")


class TestTheReportedOffset:
    """CODESYS gives a character offset that runs across both texts as if they
    were one, so an offset past the declaration is inside the implementation."""

    def test_an_offset_inside_the_declaration(self):
        at = DECL.index("iCount")
        assert build_log._from_position(at, DECL, IMPL) == (3, 5, "(Decl)")

    def test_an_offset_inside_the_implementation(self):
        at = len(DECL) + IMPL.index("IF iCount")
        assert build_log._from_position(at, DECL, IMPL) == (2, 1, "(Impl)")

    def test_no_offset_at_all(self):
        assert build_log._from_position(-1, DECL, IMPL) is None
        assert build_log._from_position(None, DECL, IMPL) is None

    def test_an_offset_past_the_end_lands_at_the_end(self):
        """Rather than raising or wrapping round to line one."""
        line, _col, section = build_log._from_position(
            len(DECL) + len(IMPL) + 500, DECL, IMPL)
        assert section == "(Impl)"
        assert line == len(IMPL.split("\n"))


class TestTheSearch:
    def test_it_finds_the_identifier_the_message_names(self):
        line, col, section = build_log.locate_message(
            "'iCount' is not defined", len(DECL), DECL, IMPL)
        assert (line, col, section) == (1, 1, "(Impl)")

    def test_it_reads_the_instead_of_form_too(self):
        assert build_log._suspects("expected ';' instead of iCount") == \
            [";", "iCount"]

    def test_the_occurrence_nearest_the_offset_wins(self):
        """A name appearing five times is five candidates, and the offset is
        the only thing that says which one the message is about."""
        near_the_end = len(DECL) + IMPL.index("iCount := 0")
        line, _col, section = build_log.locate_message(
            "'iCount' is wrong", near_the_end, DECL, IMPL)
        assert (line, section) == (3, "(Impl)")

    def test_code_in_a_declaration_wins_outright(self):
        """A statement above END_VAR is the error however far the reported
        offset is from it."""
        decl = ("FUNCTION_BLOCK Broken\n"
                "VAR\n"
                "    iCount : INT;\n"
                "    DoTheThing();\n"
                "END_VAR\n")
        line, _col, section = build_log.locate_message(
            "'DoTheThing' unexpected", len(decl) + 40, decl, IMPL)
        assert (line, section) == (4, "(Decl)")

    def test_an_assignment_above_end_var_slips_through(self):
        """":=" has a colon in it, and "has a colon" is the test for "this
        line declares something". A hint that improves where an error points,
        not a rule -- pinned here so a future edit knows it is choosing to
        change behaviour rather than discovering a bug."""
        decl = "FUNCTION_BLOCK X\nVAR\n    iCount := 1;\nEND_VAR\n"
        assert build_log._is_code_in_a_declaration(decl, 3) is False


class TestTheLastResort:
    def test_a_message_that_spells_out_its_line(self):
        assert build_log._from_message_text("Syntax error, Line: 12, Column: 3") \
            == (12, 3, "")

    def test_a_line_without_a_column(self):
        assert build_log._from_message_text("problem at line 7")[:2] == (7, 0)

    def test_a_message_that_says_nothing_about_where(self):
        assert build_log._from_message_text("something went wrong") is None


class TestLocateMessage:
    def test_nothing_to_go_on_is_no_position(self):
        """Zero, so the caller prints no position at all rather than
        dressing a guess up as an answer."""
        assert build_log.locate_message("no idea", -1, "", "") == (0, 0, "")

    def test_the_offset_answers_when_the_search_finds_nothing(self):
        at = DECL.index("iCount")
        assert build_log.locate_message("something went wrong", at, DECL, IMPL) \
            == (3, 5, "(Decl)")

    def test_the_message_text_answers_when_there_is_no_offset(self):
        assert build_log.locate_message("failed at Line: 4", -1, "", "") \
            == (4, 0, "")


class TestTheTable:
    def test_a_long_description_is_cut_to_its_column(self):
        """A format specifier pads a short string but lets a long one
        overflow, and one overflowing row breaks the whole file's alignment."""
        line = build_log.row("x" * 200, "Obj", "Line 1, Col 1")
        assert line.split(" | ")[0].endswith("...")
        assert len(line.split(" | ")[0]) == build_log.DESC_WIDTH

    def test_newlines_never_reach_the_table(self):
        assert "\n" not in build_log.row("two\nlines", "Obj", "")

    def test_no_position_leaves_the_column_empty(self):
        assert build_log.position_text(0, 0, "") == ""

    def test_the_log_starts_with_the_application_and_ends_with_the_count(self):
        lines = build_log.table("Application", ["a row"], 2, 3)
        assert lines[0] == "------ Build started: Application: Application ------"
        assert lines[-1] == "Compile complete -- 2 errors, 3 warnings"
        assert "a row" in lines


@pytest.mark.parametrize("text,expected", [
    ("VAR", False),
    ("END_VAR", False),
    ("    iCount : INT;", False),
    ("    iCount := 1;", False),
    ("    DoTheThing();", True),
])
def test_what_counts_as_code_in_a_declaration(text, expected):
    decl = "FUNCTION_BLOCK X\n" + text + "\n"
    assert build_log._is_code_in_a_declaration(decl, 2) is expected
