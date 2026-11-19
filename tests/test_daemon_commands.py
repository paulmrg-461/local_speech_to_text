"""Daemon: comandos idempotentes y permisos del socket (T3/T9)."""

from __future__ import annotations

import json
import stat
import threading
import time

from local_speech_to_text.daemon import Daemon


class FakeRecorder:
    sample_rate = 16000

    def __init__(self) -> None:
        self.is_recording = False
        self.elapsed = 0.0
        self.current_rms = 0.0


def _daemon(tmp_path) -> Daemon:
    d = Daemon.__new__(Daemon)  # sin sounddevice ni modelo
    d.recorder = FakeRecorder()
    d._lock = threading.Lock()
    d._recording_origin = None
    d.hold_status = "off"
    d.hold_listener = None
    d._partial_text = ""
    d._sock_path = tmp_path / "local-stt.sock"
    d.calls: list[str] = []

    def _start():
        d.calls.append("start")
        d.recorder.is_recording = True

    def _stop():
        d.calls.append("stop")
        d.recorder.is_recording = False
        d._recording_origin = None

    d._start_recording = _start
    d._stop_and_transcribe = _stop
    return d


def test_start_es_idempotente(tmp_path):
    d = _daemon(tmp_path)
    assert d.start_recording("socket") is True
    assert d.start_recording("socket") is False
    assert d.calls == ["start"]
    assert d._recording_origin == "socket"


def test_stop_en_idle_no_arranca_grabacion(tmp_path):
    """Regresión: 'stop' llamaba a toggle() y grababa si estaba idle."""
    d = _daemon(tmp_path)
    assert d.stop_recording() is False
    assert d.calls == []


def test_toggle_alterna(tmp_path):
    d = _daemon(tmp_path)
    d.toggle()
    assert d._recording_origin == "toggle"  # se fija antes de arrancar
    d.toggle()
    assert d.calls == ["start", "stop"]


def test_origin_wake_se_mantiene(tmp_path):
    d = _daemon(tmp_path)
    d.start_recording("wake")
    assert d._recording_origin == "wake"


def test_comando_start_stop_idempotentes(tmp_path):
    d = _daemon(tmp_path)
    assert d._handle_command("start") == "ok"
    assert d._handle_command("start") == "ok"
    assert d._handle_command("stop") == "ok"
    assert d._handle_command("stop") == "ok"
    assert d.calls == ["start", "stop"]


def test_comando_toggle_y_desconocido(tmp_path):
    d = _daemon(tmp_path)
    assert d._handle_command("toggle") == "ok"
    assert d._handle_command("") == "ok"
    assert d._handle_command("nope") == "unknown"
    assert d.calls == ["start", "stop"]


def test_status_incluye_hold_y_origen(tmp_path):
    d = _daemon(tmp_path)
    d.hold_status = "running"
    d.start_recording("hold")
    assert d._handle_command("status") == "recording origin=hold hold=running"
    d.stop_recording()
    assert d._handle_command("status") == "idle origin=- hold=running"


def test_level_incluye_hold(tmp_path):
    d = _daemon(tmp_path)
    payload = json.loads(d._handle_command("level"))
    assert payload["hold"] == "off"
    assert payload["recording"] is False


def _serve_and_stat(d: Daemon) -> int:
    d._running = True
    thread = threading.Thread(target=d._serve, daemon=True)
    thread.start()
    try:
        mode = 0
        for _ in range(150):  # el hilo puede tardar en borrar el socket viejo
            try:
                st = d._sock_path.stat()
            except FileNotFoundError:  # _serve lo borró entre exists() y stat()
                time.sleep(0.02)
                continue
            if stat.S_ISSOCK(st.st_mode):
                mode = stat.S_IMODE(st.st_mode)
                if mode == 0o600:
                    break
            time.sleep(0.02)
        return mode
    finally:
        d._running = False
        thread.join(timeout=3)


def test_socket_solo_para_el_dueno(tmp_path):
    d = _daemon(tmp_path)
    assert _serve_and_stat(d) == 0o600


def test_socket_viejo_0777_se_recrea(tmp_path):
    d = _daemon(tmp_path)
    d._sock_path.write_text("basura")  # socket viejo con permisos laxos
    d._sock_path.chmod(0o777)
    assert _serve_and_stat(d) == 0o600
