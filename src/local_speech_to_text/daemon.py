from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path


from .clipboard import copy_to_clipboard, notify, paste_via_key, play_sound
from .config import Config
from .recorder import AudioRecorder
from .text_cleaner import clean_text, numbers_to_digits
from .transcriber import Transcriber
from .vocab import apply_corrections, load_corrections, load_vocabulary


class Daemon:
    """Daemon que mantiene el modelo en VRAM y alterna grabación con Win+F."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.recorder = AudioRecorder(
            sample_rate=self.config.sample_rate,
            silence_rms=self.config.silence_rms,
            mic=getattr(self.config, "mic", None),
        )
        self.transcriber: Transcriber | None = None
        self.corrections: list[tuple[str, str]] = []
        self._lock = threading.Lock()
        self._sock_path = self.config.socket_path
        self._running = False
        self._server_thread: threading.Thread | None = None
        self._osd_proc: subprocess.Popen | None = None
        self._osd_choice: tuple[str, str] | None = None  # (backend, motivo), cacheado
        self._osd_backend_used = "tk"
        self._partial_text = ""
        self._partial_thread: threading.Thread | None = None
        self._partial_busy = False
        self._stream_text = ""  # segmentos ya transcritos (dictados largos)
        self._stream_processed = 0  # muestras ya confirmadas
        self.wake_monitor = None  # WakeWordMonitor | None
        self.hold_listener = None  # HotkeyListener | None (push-to-talk)
        self.hold_status = "off"  # off | waiting | running | no-permission | no-evdev | bad-chord
        self._recording_origin: str | None = None  # toggle|wake|hold|socket
        self.translate_mode = False  # dictar en un idioma -> salir en inglés

    def _ensure_model(self):
        if self.transcriber is None:
            print("[daemon] Cargando modelo en VRAM... (primera vez tarda ~10-20s)")
            notify("Local STT", "Cargando modelo en GPU... primera vez puede tardar")
            vocab = load_vocabulary(self.config.vocabulary_file)
            self._default_prompt = vocab or None
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
            self.transcriber.initial_prompt = self._default_prompt
            self.transcriber.task = "translate" if self.translate_mode else "transcribe"
            notify("Local STT", f"Modelo {self.config.model} listo en {self.config.device}")

    def toggle(self):
        with self._lock:
            if not self.recorder.is_recording:
                self._recording_origin = "toggle"
                self._notify_hold_started("toggle")
                self._start_recording()
            else:
                self._stop_and_transcribe()

    def start_recording(self, origin: str = "socket") -> bool:
        """Arranca si está idle. Idempotente: grabando no reinicia (RF-6)."""
        with self._lock:
            if self.recorder.is_recording:
                return False
            self._recording_origin = origin
            self._notify_hold_started(origin)
            self._start_recording()
            return True

    def stop_recording(self) -> bool:
        """Para si graba. Idempotente: en idle no hace nada (RF-6)."""
        with self._lock:
            if not self.recorder.is_recording:
                return False
            self._stop_and_transcribe()
            return True

    def _notify_hold_started(self, origin: str) -> None:
        if self.hold_listener is not None:
            self.hold_listener.machine.notify_recording_started(origin)

    def _notify_hold_stopped(self) -> None:
        if self.hold_listener is not None:
            self.hold_listener.machine.notify_recording_stopped()

    def _set_hold_status(self, status: str) -> None:
        self.hold_status = status

    def _start_hold_listener(self) -> None:
        """Push-to-talk opcional: mantiene un hilo leyendo /dev/input (evdev)."""
        if not self.config.push_to_talk:
            self.hold_status = "off"
            return
        if self.hold_listener is not None:
            return
        from .hotkey_hold import HotkeyListener, parse_chord

        chord = parse_chord(self.config.hold_key)
        if chord is None:
            self.hold_status = "bad-chord"
            print(f"[hold] hold_key inválido: {self.config.hold_key!r} (usa p. ej. 'super+f')")
            return
        listener = HotkeyListener(
            chord,
            min_ms=self.config.hold_min_ms,
            allowlist=self.config.hold_devices,
            on_start=lambda: self.start_recording("hold"),
            on_stop=self.stop_recording,
            on_status=self._set_hold_status,
        )
        if listener.start():
            self.hold_listener = listener
        self.hold_status = listener.status

    def _stop_hold_listener(self) -> None:
        if self.hold_listener is not None:
            self.hold_listener.stop()
            self.hold_listener = None
        if not self.config.push_to_talk:
            self.hold_status = "off"

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
                self._recording_origin = "wake"
                self._notify_hold_started("wake")
                self._start_recording()

    def _stop_wake_word(self) -> None:
        if self.wake_monitor:
            self.wake_monitor.stop()
            self.wake_monitor = None

    def _apply_contextual_vocab(self) -> None:
        """Vocabulario según la app enfocada (config app_vocab).

        La detección va en un hilo: kdotool es instantáneo, pero el DBus de
        KWin puede tardar/pedir interacción. El prompt se cambia al vuelo
        antes de la transcripción final (que ocurre al parar).
        """
        profiles = getattr(self.config, "app_vocab", None) or {}
        if not profiles or not self.transcriber:
            return
        from .active_window import get_active_window_name, match_profile
        from .config import _resolve_vocab
        from .vocab import load_vocabulary

        def _detect():
            try:
                window = get_active_window_name()
                profile = match_profile(window, profiles)
                if profile:
                    prompt = load_vocabulary(_resolve_vocab(profile))
                    print(f"[daemon] vocabulario contextual '{profile}' (ventana: {(window or '')[:60]})")
                    self.transcriber.initial_prompt = prompt or self._default_prompt
                else:
                    print(f"[daemon] sin perfil para '{(window or '?')[:60]}': vocabulario por defecto")
                    self.transcriber.initial_prompt = self._default_prompt
            except Exception as e:
                print(f"[daemon] detección de ventana falló: {e}")

        threading.Thread(target=_detect, daemon=True).start()

    def _start_recording(self):
        self._ensure_model()
        self._partial_text = ""
        self._stream_text = ""
        self._stream_processed = 0
        # Auto-stop por tiempo máximo en hilo aparte
        self.recorder.start()
        if self.wake_monitor:
            self.wake_monitor.pause()  # no re-disparar mientras dictas
        self._apply_contextual_vocab()
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

    def _osd_argv(self) -> tuple[list[str], str]:
        """argv del OSD y backend realmente usado (gtk|tk)."""
        from .osd_backend import find_system_python, select_backend

        backend, reason = self._osd_choice or select_backend(self.config.osd_backend)
        self._osd_choice = (backend, reason)
        sock = str(self._sock_path)
        if backend == "gtk":
            python = find_system_python()
            script = Path(__file__).with_name("osd_gtk.py")
            if python and script.exists():
                return [python, str(script), sock, "--margin", str(self.config.osd_margin_top)], "gtk"
            print("[daemon] sin python del sistema con GTK: OSD en Tk")
        return [sys.executable, "-m", "local_speech_to_text.osd", sock], "tk"

    def _launch_osd(self) -> None:
        """OSD con nivel de voz (opcional, config overlay)."""
        if not getattr(self.config, "overlay", True):
            return
        argv, backend = self._osd_argv()
        try:
            self._osd_proc = subprocess.Popen(
                argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as e:
            print(f"[daemon] OSD no lanzado: {e}")
            self._osd_proc = None
            return
        self._osd_backend_used = backend
        if backend == "gtk":
            # Si GTK muere al arrancar (typelib roto, sin display), Tk una vez.
            threading.Thread(target=self._watch_osd, args=(self._osd_proc,), daemon=True).start()

    def _watch_osd(self, proc: subprocess.Popen) -> None:
        time.sleep(0.6)
        if proc is not self._osd_proc or proc.poll() in (None, 0):
            return
        print("[daemon] OSD GTK falló al arrancar; usando Tk")
        # Recordar el fallback: no reintentar GTK en cada dictado.
        self._osd_choice = ("tk", "fallback tras fallo de GTK")
        try:
            self._osd_proc = subprocess.Popen(
                [sys.executable, "-m", "local_speech_to_text.osd", str(self._sock_path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            self._osd_backend_used = "tk"
        except Exception as e:
            print(f"[daemon] OSD Tk tampoco arrancó: {e}")
            self._osd_proc = None

    def _kill_osd(self) -> None:
        if not self._osd_proc:
            return
        proc, self._osd_proc = self._osd_proc, None
        try:
            proc.terminate()
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                proc.kill()
        except Exception:
            pass

    def _start_partial_worker(self) -> None:
        """Parciales en vivo + streaming de ventanas para dictados largos.

        Cuando el audio pendiente supera `stream_window` segundos se transcribe
        y se "confirma" (commit) al texto acumulado; el OSD muestra acumulado +
        parcial. Al parar solo se transcribe la cola final, no todo desde cero.
        """
        if not getattr(self.config, "partial_results", True):
            return

        interval = getattr(self.config, "partial_interval", 1.5)
        window = int(getattr(self.config, "stream_window", 12.0) * self.recorder.sample_rate)

        def _worker():
            while self.recorder.is_recording:
                time.sleep(interval)
                if not self.recorder.is_recording or self._partial_busy or not self.transcriber:
                    continue
                audio = self.recorder.full_audio()
                pending = audio[self._stream_processed:]
                if pending.size < 16000:  # <1s: nada que hacer
                    continue
                self._partial_busy = True
                try:
                    part = self.transcriber.transcribe_partial(pending, self.recorder.sample_rate)
                    if not self.recorder.is_recording:
                        continue  # paró durante la transcripción: lo maneja el stop
                    with self._lock:
                        if not self.recorder.is_recording:
                            continue  # segundo check: el stop entró mientras esperábamos el lock
                        if pending.size >= window and getattr(self.config, "streaming", True):
                            if part:
                                self._stream_text = (self._stream_text + " " + part).strip()
                            self._stream_processed = audio.size
                        else:
                            live = (self._stream_text + " " + part).strip() if part else self._stream_text
                            self._partial_text = live
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
            "hold": self.hold_status,
        })

    def toggle_translate(self) -> str:
        """Alterna traducción (Whisper: cualquier idioma -> inglés)."""
        self.translate_mode = not self.translate_mode
        task = "translate" if self.translate_mode else "transcribe"
        if self.transcriber:
            self.transcriber.task = task
        if self.translate_mode:
            notify("🌐 Modo traducción ON", "Dicta en tu idioma: saldrá en inglés")
        else:
            notify("Modo traducción OFF", "Dictado normal")
        print(f"[daemon] task={task}")
        return f"translate={'on' if self.translate_mode else 'off'}"

    def _stop_and_transcribe(self):
        print("[daemon] ⏹ Parando grabación...")
        notify("⏳ Transcribiendo...", "Procesando en GPU...", icon="media-record")
        self._kill_osd()
        recording = self.recorder.stop()
        self._partial_text = ""
        self._recording_origin = None
        self._notify_hold_stopped()
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
        raw = self._final_transcription(recording)
        text = clean_text(raw) if self.config.dictation_commands else raw
        if self.corrections:
            text = apply_corrections(text, self.corrections)
        if getattr(self.config, "numbers_to_digits", False):
            text = numbers_to_digits(text)
        print(f"[daemon] Transcrito en {time.time() - t0:.2f}s")

        if not text.strip():
            notify("Local STT", "No se entendió audio (silencio/ruido)", urgency="critical")
            print("[daemon] Transcripción vacía")
            return

        self._save_history(text, duration)
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

    def _final_transcription(self, recording) -> str:
        """Texto final: cola pendiente si hubo streaming; paso completo si fue corto."""
        if not self.transcriber:
            return ""
        streaming = getattr(self.config, "streaming", True) and self._stream_text
        if not streaming:
            return self.transcriber.transcribe(recording.samples, recording.sample_rate)
        # dictado largo: solo transcribir lo pendiente desde el último commit
        audio = self.recorder.full_audio()
        tail = audio[self._stream_processed:]
        print(f"[daemon] streaming: {self._stream_processed / recording.sample_rate:.0f}s ya confirmados, "
              f"cola {tail.size / recording.sample_rate:.1f}s")
        tail_text = ""
        if tail.size > recording.sample_rate // 2:  # >0.5s
            tail_text = self.transcriber.transcribe(tail, recording.sample_rate)
        return (self._stream_text + " " + tail_text).strip()

    def _save_history(self, text: str, duration: float | None = None) -> None:
        """Añade al historial JSONL (máx. 100 entradas, la última al final)."""
        try:
            path: Path = self.config.history_path
            path.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "text": text,
                "duration": round(duration, 1) if duration else None,
            }
            lines = []
            if path.exists():
                lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
            lines.append(json.dumps(entry, ensure_ascii=False))
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
        self.recorder.mic = new.mic
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
        # push-to-talk: aplicar cambios de modo/chord/devices al vuelo
        old_hold = (old.push_to_talk, old.hold_key, old.hold_min_ms, tuple(old.hold_devices))
        new_hold = (new.push_to_talk, new.hold_key, new.hold_min_ms, tuple(new.hold_devices))
        if old_hold != new_hold:
            self._stop_hold_listener()
            self._start_hold_listener()
            print(f"[daemon] push-to-talk: {self.hold_status}")
        # OSD: el backend se re-sondea en el próximo dictado
        self._osd_choice = None
        return f"ok recargado: model={new.model} lang={new.language or 'auto'}"

    # --- Socket IPC para toggle desde atajo ---
    def _handle_command(self, data: str) -> str:
        """Procesa un comando IPC y devuelve la respuesta (sin socket).

        `start`/`stop` son idempotentes: repetirlos no cambia el estado.
        """
        if data == "start":
            self.start_recording("socket")
            return "ok"
        if data == "stop":
            self.stop_recording()
            return "ok"
        if data in ("toggle", ""):
            self.toggle()
            return "ok"
        if data == "reload":
            try:
                return self.reload_config()
            except Exception as e:
                return f"error: {e}"
        if data == "translate":
            try:
                return self.toggle_translate()
            except Exception as e:
                return f"error: {e}"
        if data == "status":
            state = "recording" if self.recorder.is_recording else "idle"
            origin = self._recording_origin or "-"
            return f"{state} origin={origin} hold={self.hold_status}"
        if data == "level":
            return self._level_payload()
        return "unknown"

    def _serve(self):
        if self._sock_path.exists():
            try:
                self._sock_path.unlink()
            except Exception:
                pass
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(self._sock_path))
        srv.listen(5)
        # Solo el dueño del daemon: otro usuario local no debe arrancar el micro
        # ni parar el dictado.
        try:
            os.chmod(self._sock_path, 0o600)
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
                    if data == "quit":
                        conn.sendall(b"bye\n")
                        self.stop()
                        continue
                    conn.sendall((self._handle_command(data) + "\n").encode())
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
        self._start_hold_listener()

        modo = f"mantén {self.config.hold_key}" if self.config.push_to_talk else "presiona Win+F"
        notify("Local STT", f"Daemon listo. {modo.capitalize()} para dictar ({self.config.model} en {self.config.device})")
        print(f"[daemon] Listo. Modelo {self.config.model} en {self.config.device}. {modo.capitalize()} (o: local-stt toggle)")
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
        self._stop_hold_listener()
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
