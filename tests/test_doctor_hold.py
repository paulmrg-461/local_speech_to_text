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


def _cfg(**kw):
    from dataclasses import replace
    from pathlib import Path

    from local_speech_to_text.config import Config

    base = Config.load(config_file=Path("/no/existe.toml"))
    return replace(base, push_to_talk=True, **kw)


def test_hold_ready_sin_evdev(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "evdev", None)
    ok, why = cli._hold_ready(_cfg())
    assert ok is False
    assert "evdev" in why


def test_hold_ready_sin_grupo(monkeypatch):
    pytest.importorskip("evdev")
    monkeypatch.setattr(cli, "_input_group_ok", lambda: False)
    ok, why = cli._hold_ready(_cfg())
    assert ok is False
    assert "input" in why


def test_hold_ready_chord_invalido(monkeypatch):
    ok, why = cli._hold_ready(_cfg(hold_key="hola+f"))
    assert ok is False
    assert "hold_key" in why


def test_hold_ready_tecla_no_soportada(monkeypatch):
    import sys
    import types

    fake = types.ModuleType("evdev")
    fake.ecodes = types.SimpleNamespace(KEY_F=33)
    monkeypatch.setitem(sys.modules, "evdev", fake)
    ok, why = cli._hold_ready(_cfg(hold_key="super+xyz"))
    assert ok is False
    assert "no soportada" in why


def test_hold_ready_ok(monkeypatch):
    pytest.importorskip("evdev")
    monkeypatch.setattr(cli, "_input_group_ok", lambda: True)
    monkeypatch.setattr(cli, "_list_keyboards", lambda: [("AT Translated Set 2 keyboard", "/dev/input/event3")])
    ok, why = cli._hold_ready(_cfg())
    assert ok is True
    assert "AT Translated" in why


def test_hold_ready_allowlist_sin_coincidencias(monkeypatch):
    pytest.importorskip("evdev")
    monkeypatch.setattr(cli, "_input_group_ok", lambda: True)
    monkeypatch.setattr(cli, "_list_keyboards", lambda: [("Logitech USB Keyboard", "/dev/input/event5")])
    ok, why = cli._hold_ready(_cfg(hold_devices=["AT Translated"]))
    assert ok is False
    assert "hold_devices no coincide" in why
