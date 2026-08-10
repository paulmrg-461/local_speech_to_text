from __future__ import annotations

import os
import signal
import socket
import struct
import threading
import time
from pathlib import Path

import numpy as np

from .clipboard import copy_to_clipboard, notify, paste_via_key, play_sound
from .config import Config
from .recorder import AudioRecorder
from .transcriber import Transcriber


class Daemon:
    """Daemon que mantiene el modelo en VRAM y alterna grabación con Win+F."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.recorder = AudioRecorder(sample_rate=self.config.sample_rate)
        self.transcriber: Transcriber | None = None
        self._lock = threading.Lock()
        self._sock_path = self.config.socket_path
        self._running = False
        self._server_thread: threading.Thread | None = None

    def _ensure_model(self):
        if self.transcriber is None:
            print("[daemon] Cargando modelo en VRAM... (primera vez tarda ~10-20s)")
            notify("Local STT", "Cargando modelo en GPU... primera vez puede tardar")
            self.transcriber = Transcriber(
                model=self.config.model,
                device=self.config.device,
                compute_type=self.config.compute_type,
                language=self.config.language,
                beam_size=self.config.beam_size,
                vad_filter=self.config.vad_filter,
            )
            notify("Local STT", f"Modelo {self.config.model} listo en {self.config.device}")

    def toggle(self):
        with self._lock:
            if not self.recorder.is_recording:
                self._start_recording()
            else:
                self._stop_and_transcribe()

    def _start_recording(self):
        self._ensure_model()
        # Auto-stop por tiempo máximo en hilo aparte
        self.recorder.start()
        play_sound("start")
        notify("🎤 Escuchando...", "Habla ahora. Presiona Win+F de nuevo para terminar.", icon="audio-input-microphone")
        print("[daemon] 🎤 Grabando... Win+F para parar")

        def _watchdog():
            while self.recorder.is_recording:
                if self.recorder.elapsed > self.config.max_record_seconds:
                    print("[daemon] Máximo tiempo alcanzado, parando")
                    self.toggle()
                    break
                time.sleep(0.5)

        threading.Thread(target=_watchdog, daemon=True).start()

    def _stop_and_transcribe(self):
        print("[daemon] ⏹ Parando grabación...")
        notify("⏳ Transcribiendo...", "Procesando en GPU...", icon="media-record")
        recording = self.recorder.stop()
        play_sound("stop")

        if recording.samples.size < 800:  # <50ms a 16kHz
            notify("Local STT", "No se detectó audio", urgency="critical")
            print("[daemon] Audio vacío, ignorando")
            return

        duration = recording.samples.size / recording.sample_rate
        print(f"[daemon] Audio {duration:.2f}s, transcribiendo...")
        text = self.transcriber.transcribe(recording.samples, recording.sample_rate) if self.transcriber else ""

        if not text.strip():
            notify("Local STT", "No se entendió audio (silencio/ruido)", urgency="critical")
            print("[daemon] Transcripción vacía")
            return

        print(f"[daemon] ✅ Texto: {text}")
        ok = copy_to_clipboard(text)
        if ok:
            notify("✅ Copiado al portapapeles", f"{text[:120]}", icon="edit-paste")
        else:
            notify("Local STT", "Transcrito pero fallo al copiar", urgency="critical")

        if self.config.auto_paste:
            # delay para que el usuario no pierda foco
            time.sleep(0.15)
            pasted = paste_via_key()
            if pasted:
                print("[daemon] Auto-paste enviado (Ctrl+V)")
            else:
                print("[daemon] Haz Ctrl+V para pegar")

    # --- Socket IPC para toggle desde atajo ---
    def _serve(self):
        if self._sock_path.exists():
            try:
                self._sock_path.unlink()
            except Exception:
                pass
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(self._sock_path))
        srv.listen(5)
        # permisos
        try:
            os.chmod(self._sock_path, 0o777)
        except Exception:
            pass
        print(f"[daemon] Socket en {self._sock_path} - atajo: local-stt toggle")
        srv.settimeout(1.0)
        while self._running:
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    print(f"[daemon] socket error: {e}")
                break
            with conn:
                try:
                    data = conn.recv(1024).decode().strip()
                    if data in ("toggle", "start", "stop", ""):
                        self.toggle()
                        conn.sendall(b"ok\n")
                    elif data == "status":
                        state = "recording" if self.recorder.is_recording else "idle"
                        conn.sendall(f"{state}\n".encode())
                    elif data == "quit":
                        conn.sendall(b"bye\n")
                        self.stop()
                    else:
                        conn.sendall(b"unknown\n")
                except Exception as e:
                    print(f"[daemon] handle error: {e}")
        try:
            srv.close()
            if self._sock_path.exists():
                self._sock_path.unlink()
        except Exception:
            pass

    def start(self):
        self._ensure_model()
        self._running = True
        # Escribir pid
        try:
            self.config.pid_path.write_text(str(os.getpid()))
        except Exception:
            pass
        # Manejar señales
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, lambda *_: self.stop())
            except Exception:
                pass

        self._server_thread = threading.Thread(target=self._serve, daemon=True)
        self._server_thread.start()

        notify("Local STT", f"Daemon listo. Presiona Win+F para dictar ({self.config.model} en {self.config.device})")
        print(f"[daemon] Listo. Modelo {self.config.model} en {self.config.device}. Presiona Win+F (o: local-stt toggle)")
        print(f"[daemon] Socket: {self._sock_path} | PID: {os.getpid()}")
        try:
            while self._running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        if not self._running:
            return
        print("[daemon] Saliendo...")
        self._running = False
        if self.recorder.is_recording:
            try:
                self.recorder.stop()
            except Exception:
                pass
        notify("Local STT", "Daemon detenido")
        # limpiar pid/socket
        for p in (self.config.pid_path, self._sock_path):
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass


def send_command(cmd: str = "toggle", socket_path: Path | None = None) -> str:
    path = socket_path or Config().socket_path
    if not path.exists():
        return "daemon no corre (socket no existe). Inicia con: local-stt daemon"
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect(str(path))
        s.sendall((cmd + "\n").encode())
        resp = s.recv(1024).decode().strip()
        s.close()
        return resp
    except Exception as e:
        return f"error: {e}"
