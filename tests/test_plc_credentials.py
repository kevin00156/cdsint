# -*- coding: utf-8 -*-
"""The device login the CLI hands a watcher, and where it must never turn up.

The watcher cannot read the CLI's environment, so the CLI copies the two
variables into the command it queues (spec R4). The password is then on disk
for as long as that command file is, and nowhere else.
"""
import json

import pytest

from cds.core import commands, credentials
from cdsint import cli, target
from engine import plc_link

SECRET = "s3cret-do-not-print"
FORWARDED = ["plc login", "plc logout", "plc run", "plc stop", "plc trace"]


@pytest.fixture
def both_set(monkeypatch):
    monkeypatch.setenv(credentials.USER_ENV, "dev")
    monkeypatch.setenv(credentials.PASS_ENV, SECRET)


def picked():
    watcher = object.__new__(target.Target)
    watcher.root, watcher.instance_id, watcher.timeout = "r", "i", 1.0
    return watcher


def sent_args(monkeypatch, command, args=None):
    seen = {}

    def send(root, instance_id, cmd, timeout):
        seen.update(cmd["args"])
        return {"ok": True}
    monkeypatch.setattr(target, "send", send)
    picked().run_one(command, args or {})
    return seen


def test_both_sides_read_the_names_from_one_place():
    assert plc_link.USER_ENV is credentials.USER_ENV
    assert plc_link.PASS_ENV is credentials.PASS_ENV


@pytest.mark.parametrize("command", FORWARDED)
def test_the_login_travels_with_the_commands_that_need_it(
        monkeypatch, both_set, command):
    assert sent_args(monkeypatch, command)["credentials"] == {
        "user": "dev", "password": SECRET}


@pytest.mark.parametrize("unset", [credentials.USER_ENV,
                                   credentials.PASS_ENV])
def test_one_variable_missing_means_no_credentials_at_all(
        monkeypatch, both_set, unset):
    monkeypatch.delenv(unset)
    assert "credentials" not in sent_args(monkeypatch, "plc login")


def test_other_commands_never_carry_it(monkeypatch, both_set):
    for command in ("ping", "build", "plc connect", "trace list"):
        assert "credentials" not in sent_args(monkeypatch, command)


def test_the_caller_s_own_args_are_not_mutated(monkeypatch, both_set):
    mine = {"yes": True}
    sent_args(monkeypatch, "plc run", mine)
    assert mine == {"yes": True}


def test_it_is_in_no_output_the_caller_sees(monkeypatch, both_set, capsys):
    def send(root, instance_id, cmd, timeout):
        assert cmd["args"]["credentials"]["password"] == SECRET
        return commands.new_result(cmd, False, error="the login was refused")
    monkeypatch.setattr(target, "send", send)
    monkeypatch.setattr(target, "_resolve", lambda *a: {"instance_id": "i"})
    for extra in ([], ["--json"]):
        cli.main(["plc", "login", "--target", "i"] + extra)
    shown = capsys.readouterr()
    assert SECRET not in shown.out + shown.err


def never_gone(monkeypatch):
    monkeypatch.setattr(target.Watching, "gone", lambda self, now: False)


def test_the_command_file_is_gone_after_a_timeout(tmp_path, monkeypatch):
    never_gone(monkeypatch)
    cmd = commands.new_command("plc login", {"credentials": {
        "user": "dev", "password": SECRET}})
    assert target.send(str(tmp_path), "i", cmd, 0, poll=0.001) is None
    assert commands.list_command_ids(str(tmp_path), "i") == []


def test_the_command_file_is_gone_once_answered_too(tmp_path, monkeypatch):
    # A watcher that answers without claiming leaves the file behind; the
    # password must not outlive the wait.
    never_gone(monkeypatch)
    cmd = commands.new_command("plc login", {"credentials": {
        "user": "dev", "password": SECRET}})
    answer = commands.new_result(cmd, True)
    monkeypatch.setattr(target, "collect", lambda *a: answer)
    assert target.send(str(tmp_path), "i", cmd, 5, poll=0.001) is answer
    assert commands.list_command_ids(str(tmp_path), "i") == []


def test_the_command_file_is_gone_after_a_ctrl_c(tmp_path, monkeypatch):
    never_gone(monkeypatch)

    def interrupt(_seconds):
        raise KeyboardInterrupt()
    monkeypatch.setattr(target.time, "sleep", interrupt)
    cmd = commands.new_command("plc login")
    with pytest.raises(KeyboardInterrupt):
        target.send(str(tmp_path), "i", cmd, 5, poll=0.001)
    assert commands.list_command_ids(str(tmp_path), "i") == []


def test_the_password_is_not_in_the_result_a_body_returns(tmp_path):
    # new_result takes no args, so a record cannot echo the command's; this
    # pins that, since a future field copying `cmd` would leak it.
    cmd = commands.new_command("plc login", {"credentials": {
        "user": "dev", "password": SECRET}})
    assert SECRET not in json.dumps(commands.new_result(cmd, True))
