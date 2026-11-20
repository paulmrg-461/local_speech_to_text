

from local_speech_to_text.cli import _check_system_deps, _cheatsheet


def test_cheatsheet_menciona_lo_esencial():
    cs = _cheatsheet()
    assert "Win+F" in cs
    assert "translate" in cs
    assert "doctor" in cs
    assert "hey jarvis" in cs


def test_cheatsheet_muestra_la_frase_vosk(monkeypatch, tmp_path):
    from dataclasses import replace
    from pathlib import Path

    from local_speech_to_text.config import Config

    cfg = replace(
        Config.load(config_file=Path("/no/existe.toml")),
        wake_word_engine="vosk",
        wake_word_phrase="dev paul|devpaul",
        wake_word=True,
    )
    cs = _cheatsheet(cfg)
    assert "dev paul" in cs
    assert "hey jarvis" not in cs


def test_check_system_deps_todo_instalado(monkeypatch, capsys):
    monkeypatch.setattr("shutil.which", lambda c: True)
    assert _check_system_deps() is False
    out = capsys.readouterr().out
    assert "todo presente" not in out  # no imprime nada si falta nada... (lo imprime el caller)


def test_check_system_deps_faltantes_y_sugerencia(monkeypatch, capsys):
    monkeypatch.setattr("shutil.which", lambda c: c in ("wl-copy", "wl-paste", "wtype", "notify-send", "canberra-gtk-play", "kdotool"))
    assert _check_system_deps() is True
    out = capsys.readouterr().out
    assert "wofi" in out                      # falta
    assert "sudo pacman -S" in out           # sugerencia oficial
    assert "kdotool" not in out.split("sudo pacman")[0].split("Opcional")[0] or True
    # kdotool NO va en el pacman sugerido (es AUR):
    pacman_line = [ln for ln in out.splitlines() if "pacman -S" in ln][0]
    assert "kdotool" not in pacman_line


def test_check_system_deps_aur_se_sugiere_separado(monkeypatch, capsys):
    monkeypatch.setattr("shutil.which", lambda c: c in ("wl-copy", "wl-paste", "wtype", "notify-send", "wofi", "canberra-gtk-play"))
    assert _check_system_deps() is True
    out = capsys.readouterr().out
    assert "yay -S kdotool" in out
