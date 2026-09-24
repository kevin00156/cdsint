# -*- coding: utf-8 -*-
"""The settings file's schema, and the refusals a hand-edited file earns.

Two witnesses again, for the same reason the property names had them: a
setting nobody reads and a setting nobody writes both look exactly like a
setting that works. Here the second witness is SPEC 4.4's table, so a key
added to the code without being documented fails, and so does one renamed in
the document and not in the code.

The rest is the promise `read` makes to a person editing the file by hand
(SPEC 4.4): a name it does not know, a value of the wrong shape, or a word
`plc` does not recognise stops the whole command and says so with the table
attached.
"""
import io
import json
import os
import re

import pytest

from cds.core import settings

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(REPO_ROOT, "docs", "SPEC.md")


def documented():
    """Every setting name in SPEC 4.4's table."""
    with io.open(SPEC, encoding="utf-8") as handle:
        text = handle.read()
    section = text.split("### 4.4 ", 1)[1].split("### 4.5", 1)[0]
    names = set()
    for row in section.splitlines():
        if not row.startswith("|"):
            continue
        names.update(re.findall(r"`([a-z_]+)`", row.split("|")[1]))
    return names


def write_file(tmp_path, text):
    path = os.path.join(str(tmp_path), "Line.cdsint.json")
    with io.open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def test_the_code_and_the_spec_name_the_same_settings():
    assert set(settings.KINDS) == documented()


def test_only_sync_folder_has_no_default():
    # The one setting with nothing sensible to guess (SPEC 6.7); everything
    # else is answerable without asking anybody.
    assert set(settings.KINDS) - set(settings.DEFAULTS) == {"sync_folder"}


# -- path_for --------------------------------------------------------------

def test_path_for_puts_the_file_beside_the_project():
    assert (settings.path_for(os.path.join("C:", "p", "Line.project"))
            == os.path.join("C:", "p", "Line" + settings.SUFFIX))


def test_path_for_keeps_a_chinese_name_intact():
    # Real projects live under paths like D:\客戶\產線\..., so a name that
    # only survives ASCII is no use.
    project = os.path.join(u"D:", u"客戶", u"包裝機.project")
    assert settings.path_for(project) == os.path.join(
        u"D:", u"客戶", u"包裝機" + settings.SUFFIX)


# -- read ------------------------------------------------------------------

def test_a_missing_file_is_not_an_error(tmp_path):
    assert settings.read(os.path.join(str(tmp_path), "nothing.json")) is None


def test_read_returns_only_the_keys_the_file_holds(tmp_path):
    path = write_file(tmp_path, u'{"sync_folder": "./sync"}')
    assert settings.read(path) == {"sync_folder": "./sync"}


def test_an_unknown_key_is_refused_and_the_table_is_in_the_message(tmp_path):
    path = write_file(tmp_path, u'{"sync_folder": "./sync", "debgu": true}')
    with pytest.raises(settings.Invalid) as caught:
        settings.read(path)
    message = str(caught.value)
    assert "debgu" in message
    for name in settings.KINDS:
        assert name in message


def test_a_wrong_type_is_refused_by_name(tmp_path):
    path = write_file(tmp_path, u'{"debug": "true"}')
    with pytest.raises(settings.Invalid) as caught:
        settings.read(path)
    assert "debug" in str(caught.value)


def test_a_flag_written_as_a_number_is_refused(tmp_path):
    path = write_file(tmp_path, u'{"safety_backup": 1}')
    with pytest.raises(settings.Invalid):
        settings.read(path)


def test_a_count_written_as_a_flag_is_refused(tmp_path):
    # bool is an int in Python, so this one has to be refused deliberately.
    path = write_file(tmp_path, u'{"backup_retention_count": true}')
    with pytest.raises(settings.Invalid):
        settings.read(path)


def test_trace_memory_mb_takes_a_whole_number(tmp_path):
    path = write_file(tmp_path, u'{"trace_memory_mb": 1024}')
    assert settings.read(path) == {"trace_memory_mb": 1024}


@pytest.mark.parametrize("text", [u"true", u"256.5", u'"256"'])
def test_trace_memory_mb_of_another_type_is_refused_by_name(tmp_path, text):
    path = write_file(tmp_path, u'{"trace_memory_mb": %s}' % text)
    with pytest.raises(settings.Invalid) as caught:
        settings.read(path)
    assert "trace_memory_mb wants a whole number" in str(caught.value)


def test_broken_json_is_refused_with_the_table(tmp_path):
    path = write_file(tmp_path, u'{"sync_folder": ')
    with pytest.raises(settings.Invalid) as caught:
        settings.read(path)
    assert "sync_folder" in str(caught.value)


def test_a_json_list_at_the_top_level_is_refused(tmp_path):
    path = write_file(tmp_path, u'["sync_folder"]')
    with pytest.raises(settings.Invalid):
        settings.read(path)


# -- read: the plc list ----------------------------------------------------

def test_plc_takes_the_three_words(tmp_path):
    path = write_file(tmp_path, u'{"plc": ["connect", "download", "trace"]}')
    assert settings.read(path) == {"plc": ["connect", "download", "trace"]}


def test_plc_recognises_exactly_the_words_spec_names():
    # SPEC 6.5: connect, download and trace, one per command that talks to a
    # controller. A fourth word here without a command behind it would be a
    # gate on nothing.
    assert settings.PLC_ACTIONS == ("connect", "download", "trace")


def test_plc_accepts_them_in_capitals(tmp_path):
    path = write_file(tmp_path, u'{"plc": ["DOWNLOAD"]}')
    assert settings.read(path) == {"plc": ["download"]}


def test_a_misspelt_action_is_refused_and_printed_as_written(tmp_path):
    path = write_file(tmp_path, u'{"plc": ["downlaod"]}')
    with pytest.raises(settings.Invalid) as caught:
        settings.read(path)
    # Not corrected to "download": a typo the reader can see is one they can
    # fix, and guessing would make a PLC download depend on a spellcheck.
    assert "downlaod" in str(caught.value)


def test_plc_written_as_a_string_is_refused(tmp_path):
    # Comma-separated was the property era's shape; JSON has lists.
    path = write_file(tmp_path, u'{"plc": "connect,download"}')
    with pytest.raises(settings.Invalid):
        settings.read(path)


# -- resolve ---------------------------------------------------------------

def test_resolve_fills_in_every_default_with_its_own_type():
    values = settings.resolve({})
    assert set(values) == set(settings.KINDS) - {"sync_folder"}
    assert values["debug"] is False
    assert values["safety_backup"] is True
    assert values["backup_retention_count"] == 10
    assert values["backup_name"] == ""
    assert values["plc"] == []
    assert values["trace_memory_mb"] == 256


def test_resolve_leaves_sync_folder_out_when_nobody_set_it():
    # Absent rather than None, so "not decided" reads the same way it does in
    # the file itself.
    assert "sync_folder" not in settings.resolve({})


def test_resolve_keeps_what_the_file_said():
    values = settings.resolve({"debug": True, "sync_folder": "./sync"})
    assert values["debug"] is True
    assert values["sync_folder"] == "./sync"
    assert values["safety_backup"] is True


def test_resolve_hands_out_a_plc_list_nobody_else_shares():
    first = settings.resolve({})
    first["plc"].append("connect")
    assert settings.resolve({})["plc"] == []


# -- write -----------------------------------------------------------------

def test_write_puts_down_only_the_keys_it_was_given(tmp_path):
    path = os.path.join(str(tmp_path), "Line.cdsint.json")
    settings.write(path, {"sync_folder": "./sync"})
    with io.open(path, encoding="utf-8") as handle:
        assert json.loads(handle.read()) == {"sync_folder": "./sync"}


def test_write_replaces_what_was_there(tmp_path):
    path = os.path.join(str(tmp_path), "Line.cdsint.json")
    settings.write(path, {"sync_folder": "./sync", "debug": True})
    settings.write(path, {"sync_folder": "./other"})
    assert settings.read(path) == {"sync_folder": "./other"}


def test_what_write_puts_down_read_takes_back(tmp_path):
    path = os.path.join(str(tmp_path), "Line.cdsint.json")
    written = {"sync_folder": u"./同步", "plc": ["connect"], "debug": True}
    settings.write(path, written)
    assert settings.read(path) == written


# -- folder ----------------------------------------------------------------

PROJECT_DIR = os.path.join("C:", "p")


def test_a_dot_slash_folder_resolves_against_the_project():
    assert (settings.folder("./sync", PROJECT_DIR)
            == os.path.join(PROJECT_DIR, "sync"))


def test_a_bare_dot_is_the_project_directory_itself():
    assert settings.folder(".", PROJECT_DIR) == PROJECT_DIR


def test_a_backslash_relative_path_resolves_the_same_way():
    assert (settings.folder(".\\sync", PROJECT_DIR)
            == os.path.join(PROJECT_DIR, "sync"))


def test_an_absolute_path_is_used_as_written():
    absolute = os.path.join(os.sep + "elsewhere", "sync")
    assert settings.folder(absolute, PROJECT_DIR) == absolute


def test_a_path_on_another_drive_is_used_as_written():
    # os.path.relpath refuses to relate two drives, which is why the dialog
    # never writes one as relative and why nothing here tries to.
    assert settings.folder("D:\\sync", PROJECT_DIR) == "D:\\sync"


def test_nothing_set_means_nowhere_to_point():
    assert settings.folder("", PROJECT_DIR) is None
    assert settings.folder(None, PROJECT_DIR) is None


def test_a_relative_path_with_no_project_directory_has_no_answer():
    assert settings.folder("./sync", None) is None
