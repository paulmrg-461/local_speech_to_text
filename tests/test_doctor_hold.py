"""doctor: comprobaciones de push-to-talk (T7)."""

from __future__ import annotations

import os

import pytest

from local_speech_to_text import cli


def test_input_group_ok_root_siempre(monkeypatch):
    monkeypatch.setattr(cli.os, "geteuid", lambda: 0)
    assert cli._input_group_ok([], input_gid=993) is True


def test_input_group_ok_con_grupo(monkeypatch):
    monkeypatch.setattr(cli.os, "geteuid", lambda: 1000)
    assert cli._input_group_ok([1000, 993, 44], input_gid=993) is True


def test_input_group_ok_sin_grupo(monkeypatch):
    monkeypatch.setattr(cli.os, "geteuid", lambda: 1000)
    assert cli._input_group_ok([1000, 44], input_gid=993) is False


def test_input_group_hint_explica_riesgo():
    """RS-4: no basta con el comando, hay que advertir del keylogger."""
    hint = cli.INPUT_GROUP_HINT
    assert "usermod -aG input" in hint
    assert "keylogger" in hint
    assert "hold_devices" in hint


def test_hold_device_hint_sin_evdev(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "evdev", None)
    assert "python-evdev" in cli._hold_device_hint()


@pytest.mark.skipif(os.geteuid() == 0, reason="root siempre puede leer /dev/input")
def test_hold_device_hint_reporta_permiso_o_teclado():
    hint = cli._hold_device_hint()
    assert any(k in hint for k in ("sin permiso", "keyboard", "Keyboard", "ningún", "python-evdev"))
