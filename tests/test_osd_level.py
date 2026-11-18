import json
import socket
import threading

import numpy as np

from local_speech_to_text.config import Config
from local_speech_to_text.daemon import Daemon
from local_speech_to_text.recorder import AudioRecorder


def test_snapshot_vacio_si_no_graba():
    r = AudioRecorder()
    assert r.snapshot().size == 0


def test_snapshot_devuelve_ultimo_audio(tmp_path):
    r = AudioRecorder()
    chunk = np.ones((16000,), dtype=np.float32)  # 1s
    with r._buf_lock:
        r._buffers = [chunk, chunk, chunk]
    snap = r.snapshot(max_seconds=1.5)  # 3s de audio -> últimos 1.5s
    assert snap.size == 24000


def test_level_payload_estructura():
    d = Daemon(Config.load())
    payload = json.loads(d._level_payload())
    assert {"recording", "elapsed", "rms", "partial"} <= set(payload)
    assert payload["recording"] is False


def test_query_level_contra_socket_falso(tmp_path):
    from local_speech_to_text.osd import query_level

    sock_path = tmp_path / "test.sock"
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(sock_path))
    srv.listen(1)

    def _serve():
        conn, _ = srv.accept()
        data = conn.recv(1024).decode()
        assert data.strip() == "level"
        conn.sendall(b'{"recording": true, "elapsed": 1.0, "rms": 0.01, "partial": "hola"}\n')
        conn.close()

    t = threading.Thread(target=_serve)
    t.start()
    info = query_level(str(sock_path))
    t.join(timeout=2)
    assert info == {"recording": True, "elapsed": 1.0, "rms": 0.01, "partial": "hola"}


def test_query_level_falla_limpio_si_no_hay_socket(tmp_path):
    from local_speech_to_text.osd import query_level

    assert query_level(str(tmp_path / "no-existe.sock")) is None
