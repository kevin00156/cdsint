# -*- coding: utf-8 -*-
"""What an import actually puts into a POU, against a text document shaped
like the one the IDE hands over.

The bench accused this path of inventing a line (docs/CDSINT_PLAN.md section
7, "階段 4 追加"). It did not — the line was already on disk — but the path
had no test at all, and the branch that runs on every real IDE was the
untested one: ScriptTextDocument.text is read-only there (measured on CODESYS
3.5.21.40, ScriptEngine 4.2.0.0), so every write falls through to replace().
A fake with an assignable .text never reaches that branch.
"""
import io

import pytest

from engine import codesys_compare_engine, codesys_utils, object_content


@pytest.fixture(scope="module")
def managers():
    return object_content


@pytest.fixture(scope="module")
def utils():
    return codesys_utils


class TextDocument(object):
    """ScriptTextDocument as the IDE exposes it.

    .text is a property with no setter, so `doc.text = x` raises, exactly as
    it does on the real object. replace(new_text) is the only way in, and it
    replaces the whole document.
    """

    def __init__(self, text=u""):
        self._text = text
        self.replaced = []

    @property
    def text(self):
        return self._text

    def replace(self, new_text):
        self.replaced.append(new_text)
        self._text = new_text


class Pou(object):
    has_textual_declaration = True
    has_textual_implementation = True

    def __init__(self, declaration=u"", implementation=u""):
        self.textual_declaration = TextDocument(declaration)
        self.textual_implementation = TextDocument(implementation)

    def get_name(self):
        return "PLC_PRG"


DECL_EMPTY = u"PROGRAM PLC_PRG\nVAR\nEND_VAR"
DECL_COUNTER = u"PROGRAM PLC_PRG\nVAR\n    benchProbeCounter : DINT;\nEND_VAR"
ONE_LINE = u"benchProbeCounter := benchProbeCounter + 1;"


class TestTheFakeMatchesTheRealDocument:
    def test_text_cannot_be_assigned(self):
        doc = TextDocument(u"x := 1;")
        with pytest.raises(AttributeError):
            doc.text = u"y := 2;"


class TestUpdateObjectCode:
    def test_an_empty_implementation_gets_exactly_the_one_line(self, managers):
        """The bench case. Nothing may survive from before, nothing may be added."""
        pou = Pou(DECL_EMPTY, u"")
        assert managers.update_object_code(pou, DECL_COUNTER, ONE_LINE) is True
        assert pou.textual_implementation.text == ONE_LINE
        assert pou.textual_declaration.text == DECL_COUNTER

    def test_a_one_line_implementation_is_replaced_not_appended_to(self, managers):
        pou = Pou(DECL_COUNTER, ONE_LINE)
        other = u"benchProbeCounter := benchProbeCounter + 2;"
        assert managers.update_object_code(pou, DECL_COUNTER, other) is True
        assert pou.textual_implementation.text == other

    def test_an_implementation_can_be_emptied_again(self, managers):
        """Reverting to the original text has to leave the POU as it was."""
        pou = Pou(DECL_COUNTER, ONE_LINE)
        assert managers.update_object_code(pou, DECL_EMPTY, u"") is True
        assert pou.textual_implementation.text == u""
        assert pou.textual_declaration.text == DECL_EMPTY

    def test_the_write_goes_through_replace_exactly_once(self, managers):
        """The read-only .text branch is the one production takes; count it."""
        pou = Pou(DECL_EMPTY, u"")
        managers.update_object_code(pou, DECL_COUNTER, ONE_LINE)
        assert pou.textual_implementation.replaced == [ONE_LINE]
        assert pou.textual_declaration.replaced == [DECL_COUNTER]

    def test_matching_text_is_not_rewritten(self, managers):
        pou = Pou(DECL_COUNTER, ONE_LINE)
        assert managers.update_object_code(pou, DECL_COUNTER, ONE_LINE) is False
        assert pou.textual_implementation.replaced == []
        assert pou.textual_declaration.replaced == []


class TestTheWholeHopFromDiskToPou:
    """parse_st_file into update_object_code: what import does to one file."""

    def write(self, tmp_path, text, encoding="utf-8", newline=""):
        path = tmp_path / "PLC_PRG.st"
        with io.open(str(path), "w", encoding=encoding, newline=newline) as handle:
            handle.write(text)
        return str(path)

    def test_one_line_on_disk_is_one_line_in_the_pou(self, utils, managers, tmp_path):
        path = self.write(tmp_path, DECL_COUNTER + u"\n\n"
                          + utils.IMPL_MARKER + u"\n" + ONE_LINE)
        declaration, implementation, _ = utils.parse_st_file(path)
        pou = Pou(DECL_EMPTY, u"")
        managers.update_object_code(pou, declaration, implementation)
        assert pou.textual_implementation.text == ONE_LINE

    def test_two_lines_on_disk_are_two_lines_in_the_pou(self, utils, managers, tmp_path):
        """The bench's actual file. Import is faithful to it, which is the point:
        the stray `1;` came off the disk, not out of this code."""
        two_lines = ONE_LINE + u"\n1;"
        path = self.write(tmp_path, DECL_COUNTER + u"\n\n"
                          + utils.IMPL_MARKER + u"\n" + two_lines + u"\n")
        declaration, implementation, _ = utils.parse_st_file(path)
        pou = Pou(DECL_EMPTY, u"")
        managers.update_object_code(pou, declaration, implementation)
        assert pou.textual_implementation.text == two_lines

    def test_crlf_on_disk_does_not_reach_the_pou(self, utils, managers, tmp_path):
        path = self.write(tmp_path, DECL_COUNTER + u"\n\n"
                          + utils.IMPL_MARKER + u"\n" + ONE_LINE,
                          newline="\r\n")
        declaration, implementation, _ = utils.parse_st_file(path)
        pou = Pou(DECL_EMPTY, u"")
        managers.update_object_code(pou, declaration, implementation)
        assert u"\r" not in pou.textual_implementation.text
        assert u"\r" not in pou.textual_declaration.text


class TestAByteOrderMarkIsNotCode:
    """Windows editors put a BOM at the head of a file. It is a byte-order
    mark, not the first character of the POU.

    Measured on the bench 2026-09-06 (CODESYS 3.5.21.40, softplc copy): the
    original PLC_PRG.st with a BOM in front of it imported "successfully" and
    the build went from 0 errors to 6, all of them in PLC_PRG. Nothing cdsint
    writes has a BOM, so this only ever strips one somebody else put there.
    """

    def write(self, tmp_path, text, encoding):
        path = tmp_path / "PLC_PRG.st"
        with io.open(str(path), "w", encoding=encoding, newline="") as handle:
            handle.write(text)
        return str(path)

    def test_a_bom_does_not_reach_the_declaration(self, utils, managers, tmp_path):
        path = self.write(tmp_path, DECL_EMPTY + u"\n\n" + utils.IMPL_MARKER,
                          "utf-8-sig")
        declaration, implementation, _ = utils.parse_st_file(path)
        assert declaration == DECL_EMPTY
        pou = Pou(DECL_COUNTER, ONE_LINE)
        managers.update_object_code(pou, declaration, implementation)
        assert pou.textual_declaration.text == DECL_EMPTY

    def test_a_bom_does_not_make_a_matching_file_look_different(
            self, tmp_path):
        """Otherwise compare reports the file forever, and every import
        rewrites the POU with the mark still in it."""
        compare = codesys_compare_engine
        ide_content = DECL_EMPTY + u"\n\n// === IMPLEMENTATION ==="
        path = self.write(tmp_path, ide_content, "utf-8-sig")
        disk_content = compare.read_file(path)
        assert compare.contents_are_equal(ide_content, disk_content, False,
                                          "PLC_PRG.st")
