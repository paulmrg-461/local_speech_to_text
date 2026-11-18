from __future__ import annotations

import json
import os
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from .clipboard import copy_to_clipboard, notify, paste_via_key, play_sound
from .config import Config
from .recorder import AudioRecorder
from .text_cleaner import clean_text
from .transcriber import Transcriber
from .vocab import apply_corrections, load_corrections, load_vocabulary


class Daemon:
    """Daemon que mantiene el modelo en VRAM y alterna grabación con Win+F."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.recorder = AudioRecorder(
            sample_rate=self.config.sample_rate, silence_rms=self.config.silence_rms
        )
        self.transcriber: Transcriber | None = None
        self.corrections: list[tuple[str, str]] = []
        self._lock = threading.Lock()
        self._sock_path = self.config.socket_path
        self._running = False
        self._server_thread: threading.Thread | None = None
        self._osd_proc: subprocess.Popen | None = None
        self._partial_text = ""
        self._partial_thread: threading.Thread | None = None
        self._partial_busy = False
        self.wake_monitor = None  # WakeWordMonitor | None

    def _ensure_model(self):
        if self.transcriber is None:
            print("[daemon] Cargando modelo en VRAM... (primera vez tarda ~10-20s)")
            notify("Local STT", "Cargando modelo en GPU... primera vez puede tardar")
            vocab = load_vocabulary(self.config.vocabulary_file)
            self.corrections = load_corrections(self.config.corrections_file)
            if vocab:
                print(f"[daemon] Vocabulario activo ({len(vocab.split(', '))} términos)")
            if self.corrections:
                print(f"[daemon] Correcciones activas ({len(self.corrections)})")
            self.transcriber = Transcriber(
                model=self.config.model,
                device=self.config.device,
                compute_type=self.config.compute_type,
                language=self.config.language,
                beam_size=self.config.beam_size,
                vad_filter=self.config.vad_filter,
                initial_prompt=vocab or None,
            )
            notify("Local STT", f"Modelo {self.config.model} listo en {self.config.device}")

    def toggle(self):
        with self._lock:
            if not self.recorder.is_recording:
                self._start_recording()
            else:
                self._stop_and_transcribe()

    def _maybe_start_wake_word(self) -> None:
        """Arranca el monitor de wake word si config.wake_word está activo."""
        if self.wake_monitor or not self.config.wake_word:
            return
        try:
            from .wakeword import WakeWordMonitor, resolve_model_path

            monitor = WakeWordMonitor(
                on_wake=self._on_wake,
                model_path=resolve_model_path(self.config.wake_word_model),
                threshold=self.config.wake_word_threshold,
                sample_rate=self.config.sample_rate,
            )
            if monitor.start():
                self.wake_monitor = monitor
                notify("Local STT", f"Manos libres: di '{self.config.wake_word_model}' para dictar")
        except Exception as e:
            print(f"[daemon] wake word no arrancó: {e}")

    def _on_wake(self) -> None:
        """Llamado desde el hilo del monitor: arranca dictado si no hay ya uno."""
        with self._lock:
            if not self.recorder.is_recording:
                self._start_recording()

    def _stop_wake_word(self) -> None:
        if self.wake_monitor:
            self.wake_monitor.stop()
            self.wake_monitor = None

    def _start_recording(self):
        self._ensure_model()
        self._partial_text = ""
        # Auto-stop por tiempo máximo en hilo aparte
        self.recorder.start()
        if self.wake_monitor:
            self.wake_monitor.pause()  # no re-disparar mientras dictas
        play_sound("start")
        self._launch_osd()
        self._start_partial_worker()
        notify("🎤 Escuchando...", "Habla ahora. Presiona Win+F de nuevo para terminar.", icon="audio-input-microphone")
        print("[daemon] 🎤 Grabando... Win+F para parar")

        def _watchdog():
            while self.recorder.is_recording:
                elapsed = self.recorder.elapsed
                # Auto-stop por silencio (opcional) o por tiempo máximo
                if self.config.silence_stop and elapsed > 1.0:
                    if self.recorder.silent_ms >= self.config.silence_threshold_ms:
                        print("[daemon] Silencio detectado, parando")
                        with self._lock:
                            if self.recorder.is_recording:
                                self._stop_and_transcribe()
                        return
                if elapsed > self.config.max_record_seconds:
                    print("[daemon] Máximo tiempo alcanzado, parando")
                    with self._lock:
                        if self.recorder.is_recording:
                            self._stop_and_transcribe()
                    return
                time.sleep(0.25)

        threading.Thread(target=_watchdog, daemon=True).start()

    def _launch_osd(self) -> None:
        """OSD con nivel de voz (opcional, config overlay)."""
        if not getattr(self.config, "overlay", True):
            return
        try:
            self._osd_proc = subprocess.Popen(
                [sys.executable, "-m", "local_speech_to_text.osd", str(self._sock_path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as e:
            print(f"[daemon] OSD no lanzado: {e}")
            self._osd_proc = None

    def _kill_osd(self) -> None:
        if self._osd_proc:
            try:
                self._osd_proc.terminate()
            except Exception:
                pass
            self._osd_proc = None

    def _start_partial_worker(self) -> None:
        """Transcripción parcial en vivo (opcional, config partial_results)."""
        if not getattr(self.config, "partial_results", True):
            return

        interval = getattr(self.config, "partial_interval", 1.5)

        def _worker():
            while self.recorder.is_recording:
                time.sleep(interval)
                if not self.recorder.is_recording or self._partial_busy or not self.transcriber:
                    continue
                self._partial_busy = True
                try:
                    audio = self.recorder.snapshot(max_seconds=10)
                    if audio.size > 16000:  # mínimo ~1s
                        partial = self.transcriber.transcribe_partial(audio, self.recorder.sample_rate)
                        if partial:
                            self._partial_text = partial
                except Exception as e:
                    print(f"[daemon] parcial: {e}")
                finally:
                    self._partial_busy = False

        self._partial_thread = threading.Thread(target=_worker, daemon=True)
        self._partial_thread.start()

    def _level_payload(self) -> str:
        return json.dumps({
            "recording": self.recorder.is_recording,
            "elapsed": round(self.recorder.elapsed, 1),
            "rms": round(self.recorder.current_rms, 5),
            "partial": self._partial_text,
        })

    def _stop_and_transcribe(self):
        print("[daemon] ⏹ Parando grabación...")
        notify("⏳ Transcribiendo...", "Procesando en GPU...", icon="media-record")
        self._kill_osd()
        recording = self.recorder.stop()
        self._partial_text = ""
        if self.wake_monitor:
            self.wake_monitor.resume()
        play_sound("stop")

        if recording.samples.size < 800:  # <50ms a 16kHz
            notify("Local STT", "No se detectó audio", urgency="critical")
            print("[daemon] Audio vacío, ignorando")
            return

        duration = recording.samples.size / recording.sample_rate
        print(f"[daemon] Audio {duration:.2f}s, transcribiendo...")
        t0 = time.time()
        raw = self.transcriber.transcribe(recording.samples, recording.sample_rate) if self.transcriber else ""
        text = clean_text(raw) if self.config.dictation_commands else raw
        if self.corrections:
            text = apply_corrections(text, self.corrections)
        print(f"[daemon] Transcrito en {time.time() - t0:.2f}s")

        if not text.strip():
            notify("Local STT", "No se entendió audio (silencio/ruido)", urgency="critical")
            print("[daemon] Transcripción vacía")
            return

        self._save_history(text)
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

    def _save_history(self, text: str) -> None:
        """Añade al historial JSONL (máx. 100 entradas, la última al final)."""
        try:
            path: Path = self.config.history_path
            path.parent.mkdir(parents=True, exist_ok=True)
            entry = json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "text": text}, ensure_ascii=False)
            lines = []
            if path.exists():
                lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
            lines.append(entry)
            path.write_text("\n".join(lines[-100:]) + "\n")
        except Exception as e:
            print(f"[daemon] historial no guardado: {e}")

    def reload_config(self) -> str:
        """Relee config (TOML + env). El modelo se recarga solo si cambió."""
        old = self.config
        new = Config.load()
        changed = [k for k in ("model", "device", "compute_type") if getattr(old, k) != getattr(new, k)]
        self.config = new
        # aplicar live-settings al recorder
        self.recorder.silence_rms = new.silence_rms
        if changed:
            print(f"[daemon] Config cambió {changed}: se recargará el modelo en el próximo dictado")
            self.transcriber = None  # descarga VRAM; se recarga lazy en el próximo toggle
            self.corrections = []
        else:
            # vocab/correcciones se recargan al recargar el modelo; aplicar ya las correcciones
            from .vocab import load_corrections

            self.corrections = load_corrections(new.corrections_file)
            print("[daemon] Config recargada en caliente (modelo sin cambios)")
        # wake word: aplicar cambio al vuelo
        if new.wake_word and not self.wake_monitor:
            self._maybe_start_wake_word()
        elif not new.wake_word and self.wake_monitor:
            print("[daemon] Wake word desactivado")
            self._stop_wake_word()
        return f"ok recargado: model={new.model} lang={new.language or 'auto'}"

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
                    if data == "start":
                        if not self.recorder.is_recording:
                            self.toggle()
                        conn.sendall(b"ok\n")
                    elif data in ("stop", "toggle", ""):
                        self.toggle()
                        conn.sendall(b"ok\n")
                    elif data == "reload":
                        try:
                            conn.sendall((self.reload_config() + "\n").encode())
                        except Exception as e:
                            conn.sendall(f"error: {e}\n".encode())
                    elif data == "status":
                        state = "recording" if self.recorder.is_recording else "idle"
                        conn.sendall(f"{state}\n".encode())
                    elif data == "level":
                        conn.sendall((self._level_payload() + "\n").encode())
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
        try:  # log en tiempo real cuando la salida va a archivo/journal
            import sys

            sys.stdout.reconfigure(line_buffering=True)
            sys.stderr.reconfigure(line_buffering=True)
        except Exception:
            pass
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

        self._maybe_start_wake_word()

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
        self._kill_osd()
        self._stop_wake_word()
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
        s.settimeout(5.0)  # margen: el daemon puede estar notificando/transcribiendo
        s.connect(str(path))
        s.sendall((cmd + "\n").encode())
        resp = s.recv(1024).decode().strip()
        s.close()
        return resp
    except Exception as e:
        return f"error: {e}"
