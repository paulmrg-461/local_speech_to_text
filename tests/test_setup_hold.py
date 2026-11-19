"""cmd_setup: solo desregistra Win+F si push-to-talk puede funcionar (T8)."""

from __future__ import annotations

import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest

from local_speech_to_text import cli
from local_speech_to_text.config import Config


class Args:
    model = None
    lang = "es"
    device = None
    compute = None


class _Result:
    returncode = 0
    stdout = "doctor ok"
    stderr = ""


@pytest.fixture
def setup_env(monkeypatch, tmp_path):
    """Aísla cmd_setup de red, modelo, systemd y doctor."""
    sock = tmp_path / "sock"
    sock.write_text("")
    cfg = replace(
        Config.load(config_file=Path("/no/existe.toml")),
        push_to_talk=True,
        socket_path=sock,
    )
    monkeypatch.setattr(cli, "_config_from_args", lambda a: cfg)
    monkeypatch.setattr(cli, "_check_system_deps", lambda: False)

    fake_fw = types.ModuleType("faster_whisper")
    fake_utils = types.ModuleType("faster_whisper.utils")
    fake_utils.download_model = lambda model: None
    fake_fw.utils = fake_utils
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_fw)
    monkeypatch.setitem(sys.modules, "faster_whisper.utils", fake_utils)

    hotkey = tmp_path / "setup-hotkey.sh"
    hotkey.write_text("")
    monkeypatch.setattr(cli, "_hotkey_script", lambda: hotkey)
    monkeypatch.setattr(cli, "_service_installed", lambda **kw: True)

    calls: list[tuple[list[str], dict]] = []

    def fake_run(argv, *a, **kw):
        calls.append((argv, kw))
        return _Result()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    return cfg, calls


def _hotkey_env(calls):
    argv, kwargs = next((a, k) for a, k in calls if a and a[0] == "bash")
    return kwargs.get("env", {})


def test_setup_desregistra_win_f_si_hold_listo(monkeypatch, setup_env):
    monkeypatch.setattr(cli, "_hold_ready", lambda cfg: (True, "AT keyboard"))
    cli.cmd_setup(Args())
    calls = setup_env[1]
    assert _hotkey_env(calls)["LOCAL_STT_SKIP_TOGGLE"] == "1"


def test_setup_mantiene_win_f_si_hold_no_listo(monkeypatch, setup_env, capsys):
    monkeypatch.setattr(cli, "_hold_ready", lambda cfg: (False, "usuario fuera del grupo input"))
    cli.cmd_setup(Args())
    calls = setup_env[1]
    assert "LOCAL_STT_SKIP_TOGGLE" not in _hotkey_env(calls)
    out = capsys.readouterr().out
    assert "push_to_talk activo pero no disponible" in out
    assert "usermod -aG input" in out


def test_setup_sin_hold_no_toca_win_f(monkeypatch, setup_env):
    cfg, calls = setup_env
    object.__setattr__(cfg, "push_to_talk", False)
    cli.cmd_setup(Args())
    assert "LOCAL_STT_SKIP_TOGGLE" not in _hotkey_env(calls)
