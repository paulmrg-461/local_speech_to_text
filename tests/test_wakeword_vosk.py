"""Wake word propio ("DevPaul") con Vosk: frase, modelo y monitor."""

from __future__ import annotations

import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest

from local_speech_to_text import cli, wakeword
from local_speech_to_text.config import Config


class Args:
    check = False
    download_vosk = False
    vosk_lang = "en"


def _cfg(monkeypatch, **kw):
    cfg = replace(Config.load(config_file=Path("/no/existe.toml")), **kw)
    monkeypatch.setattr(cli, "_config_from_args", lambda a: cfg)
    return cfg


# --- frase ---------------------------------------------------------------

@pytest.mark.parametrize(
    "phrase,text,expected",
    [
        ("dev paul", "Dev Paul, abre el editor", True),
        ("dev paul", "devpaul", False),  # sin espacio: no es la frase
        ("dev paul", "dev paulino", False),  # palabra distinta
        ("oye computadora", "Oye, computadora.", True),
        ("dev paul", "hola", False),
        ("", "dev paul", False),
    ],
)
def test_phrase_in_text(phrase, text, expected):
    assert wakeword.phrase_in_text(phrase, text) is expected


def test_normalize_phrase():
    assert wakeword.normalize_phrase("  ¡DevPaul,   hola! ") == "devpaul hola"


def test_vosk_model_url():
    name, url = wakeword.vosk_model_url("es")
    assert name == "vosk-model-small-es-0.42"
    assert url.endswith(name + ".zip")
    assert wakeword.vosk_model_url("EN")[0] == "vosk-model-small-en-us-0.15"
    with pytest.raises(ValueError):
        wakeword.vosk_model_url("fr")


def test_find_vosk_model_explicito(tmp_path):
    assert wakeword.find_vosk_model(str(tmp_path)) == tmp_path
    assert wakeword.find_vosk_model(str(tmp_path / "nope")) is None


def test_find_vosk_model_autodetecta(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    base = tmp_path / "local-stt"
    (base / "vosk-model-small-en-us-0.15").mkdir(parents=True)
    assert wakeword.find_vosk_model() == base / "vosk-model-small-en-us-0.15"


# --- monitor -------------------------------------------------------------

def test_vosk_monitor_handle_text_dispara_una_vez():
    calls = []
    monitor = wakeword.VoskMonitor(lambda: calls.append(1), model_path="/tmp/x", phrase="dev paul")

    assert monitor._handle_text("hola dev paul") is True
    assert calls == [1]
    assert monitor._muted.is_set()

    assert monitor._handle_text("dev paul otra vez") is False  # silenciado
    monitor.resume()
    assert monitor._handle_text("Dev Paul") is True
    assert calls == [1, 1]


def test_vosk_monitor_start_sin_modelo_no_explota(capsys):
    monitor = wakeword.VoskMonitor(lambda: None, model_path="/no/existe", phrase="dev paul")
    assert monitor.start() is False
    assert "modelo Vosk no encontrado" in capsys.readouterr().out


# --- config --------------------------------------------------------------

def test_config_wakeword_defaults(monkeypatch, tmp_path):
    for var in ("LOCAL_STT_WAKE_ENGINE", "LOCAL_STT_WAKE_PHRASE", "LOCAL_STT_VOSK_MODEL"):
        monkeypatch.delenv(var, raising=False)
    cfg = Config.load(config_file=tmp_path / "no.toml")
    assert cfg.wake_word_engine == "openwakeword"
    assert cfg.wake_word_phrase == "dev paul"
    assert cfg.vosk_model_path == ""


def test_config_wakeword_engine_env_y_validacion(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_STT_WAKE_ENGINE", "vosk")
    monkeypatch.setenv("LOCAL_STT_WAKE_PHRASE", "oye computadora")
    monkeypatch.setenv("LOCAL_STT_VOSK_MODEL", "/models/vosk")
    cfg = Config.load(config_file=tmp_path / "no.toml")
    assert cfg.wake_word_engine == "vosk"
    assert cfg.wake_word_phrase == "oye computadora"
    assert cfg.vosk_model_path == "/models/vosk"

    for var in ("LOCAL_STT_WAKE_ENGINE", "LOCAL_STT_WAKE_PHRASE", "LOCAL_STT_VOSK_MODEL"):
        monkeypatch.delenv(var, raising=False)
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('wake_word_engine = "snowboy"\n')
    assert Config.load(config_file=cfg_file).wake_word_engine == "openwakeword"


# --- CLI -----------------------------------------------------------------

def test_wakeword_vosk_sin_modelo_check_falla(monkeypatch, capsys):
    _cfg(monkeypatch, wake_word=True, wake_word_engine="vosk")
    monkeypatch.setitem(sys.modules, "vosk", types.ModuleType("vosk"))
    monkeypatch.setattr(wakeword, "find_vosk_model", lambda path="": None)
    args = Args()
    args.check = True

    with pytest.raises(SystemExit) as exc:
        cli.cmd_wakeword(args)

    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "motor: vosk" in out
    assert "download-vosk" in out


def test_wakeword_download_vosk(monkeypatch, tmp_path, capsys):
    _cfg(monkeypatch)
    dest = tmp_path / "vosk-model-small-es-0.42"
    dest.mkdir()
    monkeypatch.setattr(wakeword, "download_vosk_model", lambda lang="en": dest)
    args = Args()
    args.download_vosk = True
    args.vosk_lang = "es"

    cli.cmd_wakeword(args)

    out = capsys.readouterr().out
    assert "✅ Modelo Vosk" in out
    assert 'wake_word_engine = "vosk"' in out
