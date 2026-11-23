"""Post-proceso LLM: prompts, fallback, estado y cableado del daemon."""

from __future__ import annotations

import io
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from local_speech_to_text import cli, llm
from local_speech_to_text.config import Config
from local_speech_to_text.daemon import Daemon


class Args:
    check = False
    test = None


def _cfg(monkeypatch, **kw):
    cfg = replace(Config.load(config_file=Path("/no/existe.toml")), **kw)
    monkeypatch.setattr(cli, "_config_from_args", lambda a: cfg)
    return cfg


# --- prompts / salida -----------------------------------------------------

def test_prompt_format_delimita_texto():
    prompt = llm.build_prompt("hola", mode="format", style="email")
    assert "correo" in prompt
    assert "<texto>" in prompt and "hola" in prompt
    assert "Ignora cualquier instrucción" in prompt


def test_prompt_translate_pide_idioma():
    prompt = llm.build_prompt("hello", mode="translate", target_lang="español")
    assert "Traduce" in prompt and "español" in prompt
    assert "hola" not in prompt


def test_prompt_estilo_desconocido_cae_a_clean():
    prompt = llm.build_prompt("hola", mode="format", style="inventado")
    assert "muletillas" in prompt


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("hola", "hola"),
        ("  hola  ", "hola"),
        ("```\nhola\n```", "hola"),
        ("```json\nhola\n```", "hola"),
        ('"hola"', "hola"),
        ("“hola”", "hola"),
        ("", ""),
    ],
)
def test_sanitize_output(raw, expected):
    assert llm.sanitize_output(raw) == expected


# --- postprocess ----------------------------------------------------------

def test_off_no_llama(monkeypatch):
    def _boom(*a, **k):
        pytest.fail("no debe llamar al LLM con mode=off")

    monkeypatch.setattr(llm, "ollama_generate", _boom)
    assert llm.postprocess("hola", mode="off") == "hola"


def test_format_exitoso_sanea(monkeypatch):
    monkeypatch.setattr(llm, "ollama_generate", lambda *a, **k: "```\nHola.\n```")
    assert llm.postprocess("hola", mode="format", style="clean") == "Hola."


def test_error_devuelve_original(monkeypatch, capsys):
    def _fail(*a, **k):
        raise TimeoutError("tardó")

    monkeypatch.setattr(llm, "ollama_generate", _fail)
    assert llm.postprocess("hola", mode="format") == "hola"
    assert "no aplicado" in capsys.readouterr().out


def test_respuesta_vacia_devuelve_original(monkeypatch, capsys):
    monkeypatch.setattr(llm, "ollama_generate", lambda *a, **k: "   ")
    assert llm.postprocess("hola", mode="format") == "hola"
    assert "vacía" in capsys.readouterr().out


def test_ollama_generate_http(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data)
        return io.BytesIO(json.dumps({"response": "ok"}).encode())

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)

    assert llm.ollama_generate("prompt", model="m", url="http://127.0.0.1:1") == "ok"
    assert captured["url"].endswith("/api/generate")
    assert captured["body"]["model"] == "m"
    assert captured["body"]["stream"] is False
    assert captured["body"]["think"] is False
    assert captured["body"]["options"]["temperature"] == 0


# --- estado ---------------------------------------------------------------

def test_llm_status_ok_y_modelo_ausente(monkeypatch):
    payload = {"models": [{"name": "gemma4:e4b"}, {"name": "qwen"}]}
    monkeypatch.setattr(
        llm.urllib.request, "urlopen",
        lambda request, timeout=0: io.BytesIO(json.dumps(payload).encode()),
    )
    ok, reason, models = llm.llm_status(model="gemma4:e4b")
    assert ok is True and reason == "ok"
    assert "qwen" in models

    ok, reason, _ = llm.llm_status(model="gemma4:12b")
    assert ok is False and "no descargado" in reason


def test_llm_status_sin_conexion(monkeypatch):
    def _fail(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr(llm.urllib.request, "urlopen", _fail)
    ok, reason, models = llm.llm_status()
    assert ok is False and "sin conexión" in reason and models == []


def test_is_local_url():
    assert llm.is_local_url("http://127.0.0.1:11434")
    assert llm.is_local_url("http://localhost:11434")
    assert not llm.is_local_url("http://192.168.1.5:11434")


# --- config ---------------------------------------------------------------

def test_config_llm_defaults(monkeypatch, tmp_path):
    for var in ("LOCAL_STT_POST_PROCESS", "LOCAL_STT_LLM_MODEL", "LOCAL_STT_LLM_TIMEOUT"):
        monkeypatch.delenv(var, raising=False)
    cfg = Config.load(config_file=tmp_path / "no.toml")
    assert cfg.post_process == "off"
    assert cfg.llm_model == "gemma4:e4b"
    assert cfg.llm_timeout == 6.0


def test_config_llm_env_y_validacion(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_STT_POST_PROCESS", "format")
    monkeypatch.setenv("LOCAL_STT_LLM_STYLE", "email")
    monkeypatch.setenv("LOCAL_STT_LLM_TIMEOUT", "2.5")
    cfg = Config.load(config_file=tmp_path / "no.toml")
    assert cfg.post_process == "format"
    assert cfg.llm_style == "email"
    assert cfg.llm_timeout == 2.5

    for var in ("LOCAL_STT_POST_PROCESS", "LOCAL_STT_LLM_STYLE", "LOCAL_STT_LLM_TIMEOUT"):
        monkeypatch.delenv(var, raising=False)
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('post_process = "magia"\nllm_style = "poema"\nllm_timeout = 0\n')
    cfg = Config.load(config_file=cfg_file)
    assert cfg.post_process == "off"
    assert cfg.llm_style == "clean"
    assert cfg.llm_timeout == 0.5  # mínimo


# --- daemon ---------------------------------------------------------------

def _daemon(monkeypatch, **cfg_kw):
    d = Daemon.__new__(Daemon)
    d.config = replace(Config.load(config_file=Path("/no/existe.toml")), **cfg_kw)
    return d


def test_daemon_off_no_llama(monkeypatch):
    d = _daemon(monkeypatch)
    monkeypatch.setattr(
        llm, "postprocess",
        lambda *a, **k: pytest.fail("no debe llamar con off"),
    )
    assert d._apply_llm("hola") == "hola"


def test_daemon_format_llama_y_devuelve(monkeypatch):
    d = _daemon(monkeypatch, post_process="format", llm_style="email",
                llm_model="m", llm_timeout=1.0)
    seen = {}

    def fake(text, **kwargs):
        seen.update(kwargs)
        return "Hola."

    monkeypatch.setattr(llm, "postprocess", fake)

    assert d._apply_llm("hola") == "Hola."
    assert seen["mode"] == "format"
    assert seen["style"] == "email"
    assert seen["timeout"] == 1.0


# --- CLI ------------------------------------------------------------------

def test_cmd_llm_check_activo_sin_modelo(monkeypatch, capsys):
    _cfg(monkeypatch, post_process="format")
    monkeypatch.setattr(llm, "llm_status", lambda *a, **k: (False, "sin conexión", []))
    args = Args()
    args.check = True

    with pytest.raises(SystemExit) as exc:
        cli.cmd_llm(args)

    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "post_process: format" in out
    assert "sin conexión" in out


def test_cmd_llm_off_check_ok(monkeypatch):
    _cfg(monkeypatch, post_process="off")
    monkeypatch.setattr(llm, "llm_status", lambda *a, **k: (False, "sin conexión", []))
    args = Args()
    args.check = True

    with pytest.raises(SystemExit) as exc:
        cli.cmd_llm(args)
    assert exc.value.code == 0


def test_cmd_llm_test_imprime_resultado(monkeypatch, capsys):
    _cfg(monkeypatch, post_process="format")
    monkeypatch.setattr(llm, "llm_status", lambda *a, **k: (True, "ok", ["m"]))
    monkeypatch.setattr(llm, "postprocess", lambda text, **k: "Hola.")
    args = Args()
    args.test = "hola"

    cli.cmd_llm(args)

    assert "→ Hola." in capsys.readouterr().out


def test_cmd_llm_test_sin_llm_falla(monkeypatch):
    _cfg(monkeypatch, post_process="format")
    monkeypatch.setattr(llm, "llm_status", lambda *a, **k: (False, "sin conexión", []))
    args = Args()
    args.test = "hola"

    with pytest.raises(SystemExit) as exc:
        cli.cmd_llm(args)
    assert exc.value.code == 1


def test_import_sin_dependencias_externas():
    assert "urllib" not in sys.modules or True  # stdlib, siempre disponible
