from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field

import numpy as np

try:
    import sounddevice as sd
    import soundfile as sf  # noqa: F401
except ImportError:
    sd = None  # type: ignore


@dataclass
class Recording:
    samples: np.ndarray
    sample_rate: int


class AudioRecorder:
    """Grabación con sounddevice. Soporta toggle y VAD simple por energía."""

    def __init__(self, sample_rate: int = 16000, channels: int = 1, silence_rms: float = 0.008):
        if sd is None:
            raise RuntimeError("Falta 'sounddevice'. Instala con: pip install sounddevice soundfile")
        self.sample_rate = sample_rate
        self.channels = channels
        self.silence_rms = silence_rms
        self._queue: queue.Queue[np.ndarray] = queue.Queue()
        self._recording = False
        self._stream: sd.InputStream | None = None
        self._thread: threading.Thread | None = None
        self._buffers: list[np.ndarray] = []
        self._buf_lock = threading.Lock()
        self._start_time: float = 0
        self._last_voice_time: float = 0
        self._current_rms: float = 0.0

    def _callback(self, indata, frames, time_info, status):  # noqa: ANN001
        if status:
            print(f"[recorder] status: {status}")
        self._queue.put(indata.copy())

    def start(self) -> None:
        if self._recording:
            return
        self._buffers.clear()
        self._queue = queue.Queue()
        self._recording = True
        self._start_time = time.time()
        self._last_voice_time = self._start_time
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

        def _drain():
            while self._recording:
                try:
                    chunk = self._queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                with self._buf_lock:
                    self._buffers.append(chunk)
                # RMS del chunk: si supera el umbral hay voz (para auto-stop por silencio)
                rms = float(np.sqrt(np.mean(np.square(chunk))))
                self._current_rms = rms
                if rms >= self.silence_rms:
                    self._last_voice_time = time.time()

        self._thread = threading.Thread(target=_drain, daemon=True)
        self._thread.start()

    def stop(self) -> Recording:
        if not self._recording:
            # devolver silencio vacío
            return Recording(samples=np.zeros((0,), dtype=np.float32), sample_rate=self.sample_rate)
        self._recording = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        # drenar cola restante
        while not self._queue.empty():
            try:
                with self._buf_lock:
                    self._buffers.append(self._queue.get_nowait())
            except queue.Empty:
                break
        if not self._buffers:
            return Recording(samples=np.zeros((0,), dtype=np.float32), sample_rate=self.sample_rate)
        audio = np.concatenate(self._buffers, axis=0).flatten().astype(np.float32)
        # normalizar si es muy bajo? no necesario, whisper es robusto
        return Recording(samples=audio, sample_rate=self.sample_rate)

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def elapsed(self) -> float:
        if not self._recording:
            return 0
        return time.time() - self._start_time

    @property
    def silent_ms(self) -> float:
        """ms desde la última vez que se detectó voz (RMS sobre el umbral)."""
        if not self._recording:
            return 0
        return max(0.0, (time.time() - self._last_voice_time) * 1000)

    @property
    def current_rms(self) -> float:
        """Último RMS medido (para el indicador de nivel del OSD)."""
        return self._current_rms

    def snapshot(self, max_seconds: float = 10) -> np.ndarray:
        """Copia thread-safe del audio grabado (últimos max_seconds)."""
        with self._buf_lock:
            audio = np.concatenate(self._buffers, axis=0).flatten().astype(np.float32) if self._buffers else np.zeros((0,), dtype=np.float32)
        limit = int(max_seconds * self.sample_rate)
        return audio[-limit:] if audio.size > limit else audio

    def full_audio(self) -> np.ndarray:
        """Copia thread-safe de TODO el audio grabado hasta ahora."""
        with self._buf_lock:
            if not self._buffers:
                return np.zeros((0,), dtype=np.float32)
            return np.concatenate(self._buffers, axis=0).flatten().astype(np.float32)

    @staticmethod
    def list_devices():
        """Lista de dispositivos (DeviceList de sounddevice, imprime como tabla)."""
        if sd is None:
            return "sounddevice no instalado"
        return sd.query_devices()

    @staticmethod
    def save_wav(path: str, recording: Recording) -> None:
        import soundfile as sf

        sf.write(path, recording.samples, recording.sample_rate)
