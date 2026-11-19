"""Versión: `--version` y coherencia con pyproject."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from local_speech_to_text import cli

ROOT = Path(__file__).resolve().parents[1]


def test_version_coincide_con_pyproject():
    expected = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert cli._version() == expected


def test_cli_version_sale_con_0(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "local-stt" in out
    assert cli._version() in out
