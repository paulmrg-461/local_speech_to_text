"""Wake word manos libres con openWakeWord (CPU, int16, 16kHz).

Modelos preentrenados incluidos en el paquete (se activan con
wake_word = true en config.toml):
  hey_jarvis (default), alexa, hey_mycroft, hey_rhasspy...
Di "hey jarvis" y el dictado empieza sin tocar el teclado.

Dependencias opcionales: pip install local-speech-to-text[wakeword]
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path

_CHUNK = 1280  # 80ms a 16kHz


def normalize_phrase(text: str) -> str:
    """'DevPaul, ¡oye!' -> 'devpaul oye' (minúsculas, sin puntuación)."""
    cleaned = "".join(c if (c.isalnum() or c.isspace()) else " " for c in (text or "").lower())
    return " ".join(cleaned.split())


def phrase_in_text(phrase: str, text: str) -> bool:
    """True si la frase aparece como palabras completas (no substring)."""
    p = normalize_phrase(phrase)
    t = normalize_phrase(text)
    return bool(p) and f" {p} " in f" {t} "


# Vosk: keyword spotting por gramática, sin entrenar modelo (CPU).
VOSK_MODELS = {
    "en": "vosk-model-small-en-us-0.15",
    "es": "vosk-model-small-es-0.42",
}
VOSK_URL = "https://alphacephei.com/vosk/models/{name}.zip"


def vosk_model_url(lang: str) -> tuple[str, str]:
    """(nombre, url) del modelo Vosk pequeño para 'en' o 'es'."""
    key = (lang or "en").lower()
    if key not in VOSK_MODELS:
        raise ValueError(f"idioma Vosk no soportado: {lang} (usa en o es)")
    name = VOSK_MODELS[key]
    return name, VOSK_URL.format(name=name)


def vosk_base_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME", "~/.local/share")
    return Path(base).expanduser() / "local-stt"


def find_vosk_model(path: str = "") -> Path | None:
    """Directorio del modelo Vosk explícito o el primero instalado."""
    if path:
        candidate = Path(path).expanduser()
        return candidate if candidate.is_dir() else None
    base = vosk_base_dir()
    if not base.is_dir():
        return None
    return next((p for p in sorted(base.glob("vosk-model-*")) if p.is_dir()), None)


def download_vosk_model(lang: str = "en", dest_dir: Path | None = None) -> Path:
    """Descarga y descomprime el modelo Vosk (~40 MB). Idempotente."""
    name, url = vosk_model_url(lang)
    base = dest_dir or vosk_base_dir()
    target = base / name
    if target.is_dir():
        return target
    base.mkdir(parents=True, exist_ok=True)
    zip_path = None
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                zip_path = Path(tmp.name)
                shutil.copyfileobj(resp, tmp)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(base)
    finally:
        if zip_path is not None:
            zip_path.unlink(missing_ok=True)
    return target



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


class VoskMonitor:
    """Keyword spotting local con Vosk: detecta la frase sin modelo entrenado.

    Misma interfaz que WakeWordMonitor (start/pause/resume/stop) para que el
    daemon no distinga motor. Pensado para frases propias ("dev paul",
    "oye computadora"); la gramática limita el decoder a la frase + [unk].
    """

    def __init__(self, on_wake, model_path: str, phrase: str = "dev paul", sample_rate: int = 16000):
        self._on_wake = on_wake
        self._model_path = str(model_path)
        self._phrase = normalize_phrase(phrase) or "dev paul"
        self._sample_rate = sample_rate
        self._muted = threading.Event()
        self._stop_flag = threading.Event()
        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stream = None
        self._rec = None

    def _load_model(self) -> None:
        if not Path(self._model_path).is_dir():
            raise RuntimeError(
                f"modelo Vosk no encontrado en {self._model_path}. "
                "Descárgalo con: local-stt wakeword --download-vosk"
            )
        import vosk

        if hasattr(vosk, "SetLogLevel"):
            vosk.SetLogLevel(-1)  # sin el ruido de logs de Kaldi
        model = vosk.Model(self._model_path)
        grammar = json.dumps([self._phrase, "[unk]"])
        self._rec = vosk.KaldiRecognizer(model, self._sample_rate, grammar)

    def _handle_text(self, text: str) -> bool:
        """True si el texto contiene la frase y no estamos silenciados."""
        if self._muted.is_set() or not phrase_in_text(self._phrase, text):
            return False
        print(f"[wakeword] frase detectada: '{self._phrase}'")
        self._muted.set()  # evita re-disparos hasta resume()
        self._on_wake()
        return True

    def _loop(self) -> None:
        import sounddevice as sd

        def _callback(indata, frames, time_info, status):  # noqa: ANN001
            self._queue.put(indata.copy())

        self._stream = sd.InputStream(
            samplerate=self._sample_rate, channels=1, dtype="int16",
            blocksize=_CHUNK, callback=_callback,
        )
        self._stream.start()
        print(f"[wakeword] escuchando (vosk): '{self._phrase}'")
        while not self._stop_flag.is_set():
            try:
                chunk = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if self._muted.is_set():
                continue
            data = chunk.tobytes()
            if self._rec.AcceptWaveform(data):
                self._handle_text(json.loads(self._rec.Result()).get("text", ""))
            else:
                self._handle_text(json.loads(self._rec.PartialResult()).get("partial", ""))
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass

    def start(self) -> bool:
        try:
            self._load_model()
        except Exception as e:
            print(f"[wakeword] vosk no disponible: {e}")
            return False
        self._stop_flag.clear()
        self._muted.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def pause(self) -> None:
        self._muted.set()

    def resume(self) -> None:
        if self._rec is not None:
            try:
                self._rec.Reset()
            except Exception:
                pass
        self._muted.clear()

    def stop(self) -> None:
        self._stop_flag.set()
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
