"""Wake word manos libres con openWakeWord (CPU, int16, 16kHz).

Modelos preentrenados incluidos en el paquete (se activan con
wake_word = true en config.toml):
  hey_jarvis (default), alexa, hey_mycroft, hey_rhasspy...
Di "hey jarvis" y el dictado empieza sin tocar el teclado.

Dependencias opcionales: pip install local-speech-to-text[wakeword]
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path

_CHUNK = 1280  # 80ms a 16kHz


def resolve_model_path(name: str) -> str:
    """Nombre ('hey_jarvis') o ruta absoluta a un .onnx custom."""
    if name.endswith(".onnx"):
        return str(Path(name).expanduser())
    try:
        import openwakeword

        models_dir = Path(openwakeword.__file__).parent / "resources" / "models"
    except ImportError:
        return name
    for candidate in (f"{name}_v0.1.onnx", f"{name}.onnx"):
        if (models_dir / candidate).exists():
            return str(models_dir / candidate)
    return name


def list_models() -> list[str]:
    """Modelos .onnx de wake word incluidos (sin los de soporte ni versión)."""
    try:
        import openwakeword

        models_dir = Path(openwakeword.__file__).parent / "resources" / "models"
    except ImportError:
        return []
    if not models_dir.is_dir():
        return []
    support = ("embedding_model", "melspectrogram", "silero_vad")
    names = {
        p.stem.replace("_v0.1", "")
        for p in models_dir.glob("*.onnx")
        if not p.stem.startswith(support)
    }
    return sorted(names)


class WakeWordMonitor:
    """Escucha continua en un hilo; llama on_wake() al detectar la palabra."""

    def __init__(self, on_wake, model_path: str, threshold: float = 0.5, sample_rate: int = 16000):
        self._on_wake = on_wake
        self._model_path = model_path
        self._threshold = threshold
        self._sample_rate = sample_rate
        self._muted = threading.Event()
        self._stop_flag = threading.Event()
        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stream = None
        self._model = None

    def _load_model(self):
        import warnings

        from openwakeword.model import Model

        with warnings.catch_warnings():
            # openWakeWord pide CUDAExecutionProvider por defecto; el wheel de
            # onnxruntime de Arch es CPU y avisa en cada arranque. El wake word
            # corre en CPU por diseño, así que se silencia ese aviso concreto.
            warnings.filterwarnings(
                "ignore",
                message=r"Specified provider 'CUDAExecutionProvider'.*",
                category=UserWarning,
            )
            self._model = Model(wakeword_model_paths=[self._model_path])
        self._model_name = list(self._model.models.keys())[0]

    def _loop(self) -> None:
        import sounddevice as sd

        def _callback(indata, frames, time_info, status):  # noqa: ANN001
            self._queue.put(indata.copy())

        self._stream = sd.InputStream(
            samplerate=self._sample_rate, channels=1, dtype="int16",
            blocksize=_CHUNK, callback=_callback,
        )
        self._stream.start()
        print(f"[wakeword] escuchando '{self._model_name}' (umbral {self._threshold})")
        while not self._stop_flag.is_set():
            try:
                chunk = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if self._muted.is_set():
                continue  # dictando: ignorar (y drenar)
            scores = self._model.predict(chunk.flatten())
            score = scores.get(self._model_name, 0.0)
            if score >= self._threshold:
                print(f"[wakeword] ¡detectado! score={score:.2f}")
                self._muted.set()  # evita re-disparos hasta resume()
                self._on_wake()
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass

    def start(self) -> bool:
        try:
            self._load_model()
        except Exception as e:
            print(f"[wakeword] no disponible: {e}")
            return False
        self._stop_flag.clear()
        self._muted.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def pause(self) -> None:
        self._muted.set()

    def resume(self) -> None:
        """Reanuda tras un dictado; pequeño margen anti eco."""
        if self._model is not None:
            self._model.reset()
        self._muted.clear()

    def stop(self) -> None:
        self._stop_flag.set()
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
