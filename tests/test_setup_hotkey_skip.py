"""setup-hotkey.sh con push-to-talk: no debe registrar Win+F."""

from __future__ import annotations

import os
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "setup-hotkey.sh"


def _stub(path: Path, log_var: str) -> None:
    path.write_text(f'#!/usr/bin/env bash\necho "$*" >> "${log_var}"\n')
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _env(tmp_path, log: Path, **extra):
    env = {
        "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "XDG_CONFIG_HOME": str(tmp_path),
        "KDE_LOG": str(log),
        "GSET_LOG": str(log),
        "LOCAL_STT_DESKTOP": "kde",
    }
    env.update(extra)
    return env


def _run(tmp_path, backend="kde", skip=False):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "calls.log"
    _stub(bin_dir / "kwriteconfig6", "KDE_LOG")
    _stub(bin_dir / "gsettings", "GSET_LOG")
    (tmp_path / "khotkeysrc").write_text("")
    env = _env(tmp_path, log)
    if skip:
        env["LOCAL_STT_SKIP_TOGGLE"] = "1"
    script = "scripts/setup-hotkey.sh"
    argv = ["bash", script, f"--{backend}"]
    import subprocess

    proc = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    return proc, log.read_text() if log.exists() else ""


def test_kde_con_push_to_talk_no_registra_win_f(tmp_path):
    proc, calls = _run(tmp_path, skip=True)
    assert proc.returncode == 0, proc.stderr
    assert "Meta+F" not in calls
    assert "Meta+Shift+F" in calls
    assert "Data --key DataCount 1" in calls
    assert "Local STT Dictado" not in calls


def test_kde_sin_push_to_talk_registra_ambos(tmp_path):
    proc, calls = _run(tmp_path, skip=False)
    assert proc.returncode == 0, proc.stderr
    assert "Meta+F" in calls
    assert "Meta+Shift+F" in calls
    assert "Data --key DataCount 2" in calls
    assert "Local STT Dictado" in calls


def test_gnome_con_push_to_talk_desactiva_binding_de_dictado(tmp_path):
    proc, calls = _run(tmp_path, backend="gnome", skip=True)
    assert proc.returncode == 0, proc.stderr
    assert "custom-local-stt/ binding " in calls
    assert "custom-local-stt-pick/ binding <Super><shift>f" in calls
    # no se asigna <Super>f al dictado
    assert "custom-local-stt/ binding <Super>f" not in calls
