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

    def __init__(self, sample_rate: int = 16000, channels: int = 1):
        if sd is None:
            raise RuntimeError("Falta 'sounddevice'. Instala con: pip install sounddevice soundfile")
        self.sample_rate = sample_rate
        self.channels = channels
        self._queue: queue.Queue[np.ndarray] = queue.Queue()
        self._recording = False
        self._stream: sd.InputStream | None = None
        self._thread: threading.Thread | None = None
        self._buffers: list[np.ndarray] = []
        self._start_time: float = 0

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
                    self._buffers.append(chunk)
                except queue.Empty:
                    continue

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

    @staticmethod
    def list_devices() -> str:
        if sd is None:
            return "sounddevice no instalado"
        return str(sd.query_devices())

    @staticmethod
    def save_wav(path: str, recording: Recording) -> None:
        import soundfile as sf

        sf.write(path, recording.samples, recording.sample_rate)
