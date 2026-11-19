"""`local-stt osd`: backend y disponibilidad sin lanzar la UI."""

from __future__ import annotations

from pathlib import Path

import pytest

from local_speech_to_text import cli, osd_backend
from local_speech_to_text.config import Config


class Args:
    check = False


def _cfg(monkeypatch, **kw):
    cfg = Config.load(config_file=Path("/no/existe.toml"))
    for key, value in kw.items():
        object.__setattr__(cfg, key, value)
    monkeypatch.setattr(cli, "_config_from_args", lambda a: cfg)
    return cfg


def test_osd_tk_informa_fallback(monkeypatch, capsys):
    _cfg(monkeypatch)
    monkeypatch.setattr(osd_backend, "select_backend", lambda forced="auto", **kw: ("tk", "sesión x11"))
    monkeypatch.setattr(osd_backend, "find_system_python", lambda: "/usr/bin/python3")

    cli.cmd_osd(Args())

    out = capsys.readouterr().out
    assert "tk · sesión x11" in out
    assert "overlay: on" in out
    assert "margen: 80px" in out


def test_osd_gtk_sin_dependencias_sugiere_pacman(monkeypatch, capsys):
    _cfg(monkeypatch)
    monkeypatch.setattr(osd_backend, "select_backend", lambda forced="auto", **kw: ("gtk", "wayland"))
    monkeypatch.setattr(osd_backend, "find_system_python", lambda: "/usr/bin/python3")
    monkeypatch.setattr(osd_backend, "gtk_layer_available", lambda **kw: False)
    args = Args()
    args.check = True

    with pytest.raises(SystemExit) as exc:
        cli.cmd_osd(args)

    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "gtk4-layer-shell" in out
    assert "pacman -S" in out


def test_osd_gtk_disponible_check_ok(monkeypatch, capsys):
    _cfg(monkeypatch)
    monkeypatch.setattr(osd_backend, "select_backend", lambda forced="auto", **kw: ("gtk", "wayland"))
    monkeypatch.setattr(osd_backend, "find_system_python", lambda: "/usr/bin/python3")
    monkeypatch.setattr(osd_backend, "gtk_layer_available", lambda **kw: True)
    args = Args()
    args.check = True

    with pytest.raises(SystemExit) as exc:
        cli.cmd_osd(args)
    assert exc.value.code == 0

    out = capsys.readouterr().out
    assert "sí" in out
