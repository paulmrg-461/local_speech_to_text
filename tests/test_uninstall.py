
import pytest

from local_speech_to_text.cli import _strip_gnome_bindings


def test_strip_gnome_bindings_quita_solo_las_nuestras():
    existing = "['/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom-local-stt/', '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom-local-stt-pick/', '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom-screen/']"
    out = _strip_gnome_bindings(existing)
    assert "custom-local-stt" not in out
    assert "custom-screen" in out


def test_strip_gnome_bindings_vacia_resultante():
    assert _strip_gnome_bindings("['/org/gnome/.../custom-local-stt/']") == "@as []"


def test_strip_gnome_bindings_lista_vacia_de_origen():
    assert _strip_gnome_bindings("@as []") == "@as []"


def test_strip_gnome_bindings_mantiene_otras_dos():
    existing = "['/a/custom-local-stt/', '/b/otro/', '/c/tercero/']"
    out = _strip_gnome_bindings(existing)
    assert out.count("'") == 4  # dos entradas


def test_uninstall_sin_yes_no_hace_nada(monkeypatch, capsys):
    """Sin --yes solo avisa y sale 1, sin tocar el sistema."""
    from local_speech_to_text import cli

    calls = []
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: calls.append(a) or type("R", (), {"returncode": 0})())

    class Args:
        yes = False
        purge = False

    with pytest.raises(SystemExit) as e:
        cli.cmd_uninstall(Args())
    assert e.value.code == 1
    assert calls == []  # no ejecutó nada
    assert "--yes" in capsys.readouterr().out
