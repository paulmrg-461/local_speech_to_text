"""`local-stt keyboards`: ayuda a rellenar hold_devices sin adivinar."""

from __future__ import annotations

import pytest

from local_speech_to_text import cli
from local_speech_to_text.config import Config


class Args:
    model = None
    lang = "es"
    device = None
    compute = None


def _cfg(monkeypatch, devices):
    from dataclasses import replace
    from pathlib import Path

    cfg = replace(Config.load(config_file=Path("/no/existe.toml")), hold_devices=devices)
    monkeypatch.setattr(cli, "_config_from_args", lambda a: cfg)


def test_keyboards_marca_los_que_coinciden(monkeypatch, capsys):
    _cfg(monkeypatch, ["AT Translated"])
    monkeypatch.setattr(
        cli, "_list_keyboards",
        lambda: [("AT Translated Set 2 keyboard", "/dev/input/event3"),
                 ("Logitech USB Keyboard", "/dev/input/event5")],
    )

    cli.cmd_keyboards(Args())

    out = capsys.readouterr().out
    at_line = next(ln for ln in out.splitlines() if "AT Translated" in ln and "event3" in ln)
    logi_line = next(ln for ln in out.splitlines() if "Logitech" in ln and "event5" in ln)
    assert "✅" in at_line
    assert "✅" not in logi_line
    assert "hold_devices" in out


def test_keyboards_sin_allowlist_marca_todos(monkeypatch, capsys):
    _cfg(monkeypatch, [])
    monkeypatch.setattr(cli, "_list_keyboards", lambda: [("A", "/dev/input/event1")])

    cli.cmd_keyboards(Args())

    out = capsys.readouterr().out
    assert "vacía" in out
    assert "✅" in out


def test_keyboards_sin_evdev(monkeypatch, capsys):
    _cfg(monkeypatch, [])

    def _boom():
        raise ImportError("no evdev")

    monkeypatch.setattr(cli, "_list_keyboards", _boom)

    with pytest.raises(SystemExit) as exc:
        cli.cmd_keyboards(Args())
    assert exc.value.code == 1
    assert "python-evdev" in capsys.readouterr().out


def test_keyboards_sin_permiso(monkeypatch, capsys):
    _cfg(monkeypatch, [])

    def _denied():
        raise PermissionError("denied")

    monkeypatch.setattr(cli, "_list_keyboards", _denied)

    with pytest.raises(SystemExit) as exc:
        cli.cmd_keyboards(Args())
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "usermod -aG input" in out
    assert "keylogger" in out
