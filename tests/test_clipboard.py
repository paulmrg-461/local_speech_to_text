import pytest

from local_speech_to_text import clipboard as cb


def test_clipboard_matches_ignora_salto_final():
    assert cb._clipboard_matches("hola mundo", "hola mundo\n")
    assert cb._clipboard_matches("línea\nmúltiple", "línea\nmúltiple\n")
    assert not cb._clipboard_matches("hola", "adiós")
    assert not cb._clipboard_matches("hola", None)
    assert not cb._clipboard_matches("hola", "")


def test_copy_vacio_falla_rapido():
    assert cb.copy_to_clipboard("") is False


def test_copy_verifica_y_reintenta(monkeypatch, capsys):
    """Simula que la 1ª copia no llega al clipboard y la 2ª sí."""
    calls = {"n": 0}

    monkeypatch.setattr(cb.shutil, "which", lambda c: c == "wl-copy")
    monkeypatch.setattr(cb, "_run", lambda *a, **k: True)
    monkeypatch.setattr(cb, "_read_clipboard",
                        lambda *a, **k: "hola" if calls["n"] >= 2 else None)

    real_copy_once = cb._copy_once

    def _counting_copy(text):
        calls["n"] += 1
        return real_copy_once(text)

    monkeypatch.setattr(cb, "_copy_once", _counting_copy)
    assert cb.copy_to_clipboard("hola") is True
    assert calls["n"] == 2  # reintentó
    assert "reintentando" in capsys.readouterr().out


def test_copy_falla_tras_reintentos(monkeypatch, capsys):
    monkeypatch.setattr(cb.shutil, "which", lambda c: c == "wl-copy")
    monkeypatch.setattr(cb, "_run", lambda *a, **k: True)
    monkeypatch.setattr(cb, "_read_clipboard", lambda *a, **k: None)
    assert cb.copy_to_clipboard("hola") is False
    assert "no llegó" in capsys.readouterr().out


@pytest.mark.parametrize("backend", [("wl-copy", "wl-paste"), ("xclip", "xclip"), ("xsel", "xsel")])
def test_read_clipboard_preferencia_de_backends(monkeypatch, backend):
    import subprocess as sp

    copy_tool, read_tool = backend
    monkeypatch.setattr(cb.shutil, "which", lambda c: c == read_tool)

    class FakeResult:
        returncode = 0
        stdout = "leído".encode()

    seen = {}

    def fake_run(cmd, *a, **k):
        seen["cmd"] = cmd
        return FakeResult()

    monkeypatch.setattr(sp, "run", fake_run)
    assert cb._read_clipboard() == "leído"
    assert seen["cmd"][0] == read_tool
