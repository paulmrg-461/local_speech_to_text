"""`local-stt wakeword`: modelo activo, ruta y modelos incluidos."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from local_speech_to_text import cli, wakeword
from local_speech_to_text.config import Config


class Args:
    check = False


def _cfg(monkeypatch, **kw):
    cfg = Config.load(config_file=Path("/no/existe.toml"))
    for key, value in kw.items():
        object.__setattr__(cfg, key, value)
    monkeypatch.setattr(cli, "_config_from_args", lambda a: cfg)
    return cfg


def _fake_openwakeword(monkeypatch, tmp_path, files: list[str]):
    resources = tmp_path / "oww" / "resources" / "models"
    resources.mkdir(parents=True)
    for name in files:
        (resources / name).write_bytes(b"x")
    module = types.ModuleType("openwakeword")
    module.__file__ = str(tmp_path / "oww" / "__init__.py")
    monkeypatch.setitem(sys.modules, "openwakeword", module)
    return module


def test_list_models_sin_openwakeword(monkeypatch):
    monkeypatch.setitem(sys.modules, "openwakeword", None)
    assert wakeword.list_models() == []


def test_list_models_deduplica_version(monkeypatch, tmp_path):
    _fake_openwakeword(monkeypatch, tmp_path,
                       ["hey_jarvis_v0.1.onnx", "alexa_v0.1.onnx", "custom.onnx",
                        "melspectrogram.onnx", "embedding_model.onnx", "silero_vad.onnx",
                        "ignore.txt"])
    assert wakeword.list_models() == ["alexa", "custom", "hey_jarvis"]


def test_wakeword_desactivado_muestra_modelos(monkeypatch, tmp_path, capsys):
    _cfg(monkeypatch)
    _fake_openwakeword(monkeypatch, tmp_path, ["hey_jarvis_v0.1.onnx"])

    cli.cmd_wakeword(Args())

    out = capsys.readouterr().out
    assert "wake_word: off" in out
    assert "hey_jarvis" in out
    assert "(ok)" in out


def test_wakeword_activo_con_ruta_custom_valida(monkeypatch, tmp_path, capsys):
    custom = tmp_path / "mi_modelo.onnx"
    custom.write_bytes(b"x")
    _cfg(monkeypatch, wake_word=True, wake_word_model=str(custom))
    monkeypatch.setitem(sys.modules, "openwakeword", None)

    cli.cmd_wakeword(Args())

    out = capsys.readouterr().out
    assert "wake_word: on" in out
    assert "(ok)" in out


def test_wakeword_activo_sin_modelo_check_falla(monkeypatch, capsys):
    _cfg(monkeypatch, wake_word=True, wake_word_model="modelo_inexistente")
    monkeypatch.setitem(sys.modules, "openwakeword", None)
    args = Args()
    args.check = True

    with pytest.raises(SystemExit) as exc:
        cli.cmd_wakeword(args)

    assert exc.value.code == 1
    assert "no existe" in capsys.readouterr().out
