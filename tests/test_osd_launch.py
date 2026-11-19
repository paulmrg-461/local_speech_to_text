"""OSD: argv por backend, fallback a Tk y limpieza (T4)."""

from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from local_speech_to_text import osd_backend
from local_speech_to_text.config import Config
from local_speech_to_text.daemon import Daemon


class FakeProc:
    def __init__(self, rc: int | None = None) -> None:
        self._rc = rc
        self.terminated = False
        self.killed = False

    def poll(self):
        return self._rc

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        if self._rc is None:
            raise subprocess.TimeoutExpired("osd", timeout or 0)
        return self._rc


def _daemon(monkeypatch, backend="auto", margin=80, overlay=True):
    d = Daemon.__new__(Daemon)
    d.config = replace(
        Config.load(config_file=Path("/no/existe.toml")),
        osd_backend=backend,
        osd_margin_top=margin,
        overlay=overlay,
    )
    d._sock_path = Path("/tmp/local-stt-test.sock")
    d._osd_proc = None
    d._osd_choice = None
    d._osd_backend_used = "tk"
    return d


def test_argv_gtk_con_python_del_sistema(monkeypatch):
    d = _daemon(monkeypatch, backend="auto", margin=120)
    monkeypatch.setattr(osd_backend, "select_backend", lambda forced="auto", **kw: ("gtk", "wayland"))
    monkeypatch.setattr(osd_backend, "find_system_python", lambda: "/usr/bin/python3")

    argv, backend = d._osd_argv()

    assert backend == "gtk"
    assert argv[0] == "/usr/bin/python3"
    assert argv[1].endswith("osd_gtk.py")
    assert argv[2] == str(d._sock_path)
    assert argv[-2:] == ["--margin", "120"]


def test_argv_tk_si_select_dice_tk(monkeypatch):
    d = _daemon(monkeypatch, backend="tk")
    monkeypatch.setattr(osd_backend, "select_backend", lambda forced="auto", **kw: ("tk", "x11"))

    argv, backend = d._osd_argv()

    assert backend == "tk"
    assert argv[1:3] == ["-m", "local_speech_to_text.osd"]


def test_argv_tk_si_no_hay_python_de_sistema(monkeypatch):
    d = _daemon(monkeypatch, backend="auto")
    monkeypatch.setattr(osd_backend, "select_backend", lambda forced="auto", **kw: ("gtk", "wayland"))
    monkeypatch.setattr(osd_backend, "find_system_python", lambda: None)

    argv, backend = d._osd_argv()

    assert backend == "tk"
    assert "-m" in argv


def test_overlay_apagado_no_lanza_nada(monkeypatch):
    d = _daemon(monkeypatch, overlay=False)

    def _boom(*a, **k):
        pytest.fail("no debe lanzar el OSD con overlay=false")

    monkeypatch.setattr(subprocess, "Popen", _boom)
    d._launch_osd()
    assert d._osd_proc is None


def test_launch_gtk_arranca_vigilante(monkeypatch):
    d = _daemon(monkeypatch)
    monkeypatch.setattr(osd_backend, "select_backend", lambda forced="auto", **kw: ("gtk", "wayland"))
    monkeypatch.setattr(osd_backend, "find_system_python", lambda: "/usr/bin/python3")

    started = {}

    class DummyThread:
        def __init__(self, target=None, args=(), daemon=None, **kw):
            started["target"] = target
            started["args"] = args

        def start(self):
            started["started"] = True

    import local_speech_to_text.daemon as dm

    monkeypatch.setattr(dm.threading, "Thread", DummyThread)
    monkeypatch.setattr(dm.subprocess, "Popen", lambda argv, **kw: FakeProc())

    d._launch_osd()

    assert d._osd_backend_used == "gtk"
    assert started["started"] is True
    assert started["target"] == d._watch_osd


def test_watch_hace_fallback_a_tk(monkeypatch):
    d = _daemon(monkeypatch)
    dead = FakeProc(rc=2)
    d._osd_proc = dead
    d._osd_backend_used = "gtk"

    launched = []

    def fake_popen(argv, **kw):
        launched.append(argv)
        return FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr("time.sleep", lambda *_: None)

    d._watch_osd(dead)

    assert len(launched) == 1
    assert launched[0][1:3] == ["-m", "local_speech_to_text.osd"]
    assert d._osd_backend_used == "tk"


def test_watch_no_interfiere_si_el_osd_ya_se_paro(monkeypatch):
    d = _daemon(monkeypatch)
    d._osd_proc = None  # _kill_osd ya lo limpió

    def _boom(*a, **k):
        pytest.fail("no debe relanzar Tk si el OSD se paró")

    monkeypatch.setattr(subprocess, "Popen", _boom)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    d._watch_osd(FakeProc(rc=2))


def test_kill_osd_termina_y_limpia(monkeypatch):
    d = _daemon(monkeypatch)
    proc = FakeProc(rc=0)
    d._osd_proc = proc

    d._kill_osd()

    assert proc.terminated is True
    assert d._osd_proc is None


def test_kill_osd_mata_si_no_muere(monkeypatch):
    d = _daemon(monkeypatch)
    proc = FakeProc(rc=None)  # wait() lanza TimeoutExpired
    d._osd_proc = proc

    d._kill_osd()

    assert proc.terminated is True
    assert proc.killed is True
    assert d._osd_proc is None


def test_config_osd_defaults_y_env(monkeypatch, tmp_path):
    for var in ("LOCAL_STT_OSD_BACKEND", "LOCAL_STT_OSD_MARGIN"):
        monkeypatch.delenv(var, raising=False)
    cfg = Config.load(config_file=tmp_path / "no.toml")
    assert cfg.osd_backend == "auto"
    assert cfg.osd_margin_top == 80

    monkeypatch.setenv("LOCAL_STT_OSD_BACKEND", "gtk")
    monkeypatch.setenv("LOCAL_STT_OSD_MARGIN", "140")
    cfg = Config.load(config_file=tmp_path / "no.toml")
    assert cfg.osd_backend == "gtk"
    assert cfg.osd_margin_top == 140


def test_config_osd_toml_y_margen_negativo(monkeypatch, tmp_path):
    for var in ("LOCAL_STT_OSD_BACKEND", "LOCAL_STT_OSD_MARGIN"):
        monkeypatch.delenv(var, raising=False)
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('osd_backend = "tk"\nosd_margin_top = -20\n')
    cfg = Config.load(config_file=cfg_file)
    assert cfg.osd_backend == "tk"
    assert cfg.osd_margin_top == 0
