"""`local-stt history --reprocess`: reaplica la config sin perder el original."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from local_speech_to_text import cli
from local_speech_to_text.config import Config


class Args:
    count = 10
    copy = None
    reprocess = False


def _setup(monkeypatch, tmp_path, **cfg_kw):
    history = tmp_path / "history.jsonl"
    cfg = replace(
        Config.load(config_file=Path("/no/existe.toml")),
        history_path=history,
        corrections_file=tmp_path / "corrections.txt",
        **cfg_kw,
    )
    monkeypatch.setattr(cli, "_config_from_args", lambda a: cfg)
    return history


def _write(path: Path, texts: list[str]) -> None:
    path.write_text(
        "\n".join(json.dumps({"ts": "2026-11-19T10:00:00", "text": t}, ensure_ascii=False)
                  for t in texts) + "\n"
    )


def test_reprocess_aplica_puntuacion_y_numeros(monkeypatch, tmp_path, capsys):
    history = _setup(monkeypatch, tmp_path, dictation_commands=True, numbers_to_digits=True)
    _write(history, ["hola punto", "veintitrés"])

    args = Args()
    args.reprocess = True
    cli.cmd_history(args)

    entries = [json.loads(ln) for ln in history.read_text().splitlines()]
    assert entries[0]["text"] == "Hola."
    assert entries[1]["text"] == "23"
    backup = history.with_name(history.name + ".bak")
    assert "hola punto" in backup.read_text()
    assert "2/2" in capsys.readouterr().out


def test_reprocess_sin_cambios_no_toca_el_archivo(monkeypatch, tmp_path, capsys):
    history = _setup(monkeypatch, tmp_path, dictation_commands=True, numbers_to_digits=False)
    _write(history, ["Hola."])
    before = history.read_text()

    args = Args()
    args.reprocess = True
    cli.cmd_history(args)

    assert history.read_text() == before
    assert not history.with_name(history.name + ".bak").exists()
    assert "Nada que reprocesar" in capsys.readouterr().out


def test_reprocess_respeta_el_orden_y_los_metadatos(monkeypatch, tmp_path):
    history = _setup(monkeypatch, tmp_path, dictation_commands=True)
    _write(history, ["uno punto", "dos punto"])

    args = Args()
    args.reprocess = True
    cli.cmd_history(args)

    entries = [json.loads(ln) for ln in history.read_text().splitlines()]
    assert [e["text"] for e in entries] == ["Uno.", "Dos."]
    assert all(e["ts"] == "2026-11-19T10:00:00" for e in entries)
