# -*- coding: utf-8 -*-
"""calculate_hash is how the compare decides a file changed, untested until now.

Every `.st` on disk is compared to the IDE by this CRC32, so if it were ever
wrong about two different contents, an import would skip the object and say
everything was in sync. Nothing exercised it directly.

The case worth pinning is a comment with Chinese in it, because that is where
the two runtimes could part company. CPython 3 takes the `isinstance(content,
str)` branch and encodes to UTF-8 first; IronPython 2.7 has `str` and
`unicode` as the same type, so text takes that branch there too and the bytes
that reach zlib are the same. These assertions prove only the CPython half --
the other half is an argument about types, and PRINCIPLES 11 says to say
which of the two a claim rests on.
"""
import zlib

from engine.codesys_utils import calculate_hash

A_COMMENT = u"(* 馬達啟動延遲 *)"
ITS_BYTES = A_COMMENT.encode("utf-8")
EXPECTED = "%08X" % (zlib.crc32(ITS_BYTES) & 0xFFFFFFFF)


def test_text_with_chinese_in_it_hashes_as_its_utf_8_bytes():
    assert calculate_hash(A_COMMENT) == EXPECTED


def test_the_same_content_as_bytes_gives_the_same_answer():
    # The compare reads some content as text and some already encoded; if
    # these two disagreed, the same file would look changed on alternate runs.
    assert calculate_hash(ITS_BYTES) == EXPECTED


def test_the_answer_is_eight_upper_case_hex_digits():
    # The width is load-bearing: it goes into sync_cache.json and a run that
    # dropped a leading zero would not match the entry it wrote last time.
    assert len(EXPECTED) == 8
    assert EXPECTED == EXPECTED.upper()
    int(EXPECTED, 16)


def test_nothing_to_hash_is_the_empty_string_not_a_hash_of_nothing():
    # "" is how the callers spell "there was no content here". A real CRC of
    # b"" is 00000000, which is a value, and a value would read as content.
    assert calculate_hash(None) == ""


def test_two_different_comments_do_not_collide():
    assert calculate_hash(A_COMMENT) != calculate_hash(u"(* 馬達停止延遲 *)")
