from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path

try:  # Python 3.11+; en 3.10 se ignora el archivo de config
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]


def default_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME", "~/.config")
    return Path(base).expanduser() / "local-stt" / "config.toml"


def default_history_path() -> Path:
    base = os.environ.get("XDG_DATA_HOME", "~/.local/share")
    return Path(base).expanduser() / "local-stt" / "history.jsonl"


def default_log_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME", "~/.local/state")
    return Path(base).expanduser() / "local-stt"


# Variable de entorno por campo. El entorno SIEMPRE gana sobre el TOML,
# y los overrides del CLI ganan sobre todo.
_ENV_MAP = {
    "model": "LOCAL_STT_MODEL",
    "language": "LOCAL_STT_LANG",
    "device": "LOCAL_STT_DEVICE",
    "compute_type": "LOCAL_STT_COMPUTE",
    "beam_size": "LOCAL_STT_BEAM",
    "max_record_seconds": "LOCAL_STT_MAX_SECS",
    "auto_paste": "LOCAL_STT_AUTO_PASTE",
    "dictation_commands": "LOCAL_STT_DICTATION_COMMANDS",
    "silence_stop": "LOCAL_STT_SILENCE_STOP",
    "silence_rms": "LOCAL_STT_SILENCE_RMS",
    "silence_threshold_ms": "LOCAL_STT_SILENCE_MS",
    "vad_filter": "LOCAL_STT_VAD",
    "vocabulary_file": "LOCAL_STT_VOCAB",
    "corrections_file": "LOCAL_STT_CORRECTIONS",
    "overlay": "LOCAL_STT_OVERLAY",
    "partial_results": "LOCAL_STT_PARTIAL",
    "partial_interval": "LOCAL_STT_PARTIAL_SECS",
    "wake_word": "LOCAL_STT_WAKE_WORD",
    "wake_word_model": "LOCAL_STT_WAKE_MODEL",
    "wake_word_threshold": "LOCAL_STT_WAKE_THRESHOLD",
    "wake_word_engine": "LOCAL_STT_WAKE_ENGINE",
    "wake_word_phrase": "LOCAL_STT_WAKE_PHRASE",
    "vosk_model_path": "LOCAL_STT_VOSK_MODEL",
    # post-proceso con LLM local
    "post_process": "LOCAL_STT_POST_PROCESS",
    "llm_model": "LOCAL_STT_LLM_MODEL",
    "llm_url": "LOCAL_STT_LLM_URL",
    "llm_timeout": "LOCAL_STT_LLM_TIMEOUT",
    "llm_style": "LOCAL_STT_LLM_STYLE",
    "llm_target_lang": "LOCAL_STT_LLM_LANG",
    "numbers_to_digits": "LOCAL_STT_NUMBERS",
    "streaming": "LOCAL_STT_STREAMING",
    "stream_window": "LOCAL_STT_STREAM_WINDOW",
    "mic": "LOCAL_STT_MIC",
    # push-to-talk (mantener tecla para dictar)
    "push_to_talk": "LOCAL_STT_PUSH_TO_TALK",
    "hold_key": "LOCAL_STT_HOLD_KEY",
    "hold_min_ms": "LOCAL_STT_HOLD_MIN_MS",
    "hold_devices": "LOCAL_STT_HOLD_DEVICES",
    # OSD (indicador flotante)
    "osd_backend": "LOCAL_STT_OSD_BACKEND",
    "osd_margin_top": "LOCAL_STT_OSD_MARGIN",
    "osd_monitor": "LOCAL_STT_OSD_MONITOR",
}

_DEFAULTS = {
    "model": "large-v3-turbo",  # sweet spot RTX 5070 12GB: 6x más rápido que large-v3
    "language": "es",  # None = autodetect
    "device": "cuda",
    "compute_type": "float16",
    "sample_rate": 16000,
    "beam_size": 5,
    "max_record_seconds": 120,
    "auto_paste": True,
    "dictation_commands": True,
    "silence_stop": False,  # True = parar solo tras N ms de silencio
    "silence_rms": 0.008,  # umbral de energía para "hay voz"
    "silence_threshold_ms": 1500,
    "vad_filter": True,  # VAD de faster-whisper (filtra silencios antes de transcribir)
    "overlay": True,  # OSD flotante con nivel de voz al grabar
    "partial_results": True,  # transcripción parcial en vivo (se muestra en el OSD)
    "partial_interval": 1.5,  # segundos entre parciales
    "wake_word": False,  # true: "hey jarvis" arranca el dictado sin teclado
    "wake_word_model": "hey_jarvis",  # o ruta a .onnx custom
    "wake_word_threshold": 0.5,
    "wake_word_engine": "openwakeword",  # openwakeword | vosk (frase propia)
    "wake_word_phrase": "dev paul",  # solo vosk
    "vosk_model_path": "",  # vacío = ~/.local/share/local-stt/vosk-model-*
    # Post-proceso opcional con LLM local (Ollama)
    "post_process": "off",  # off | format | translate
    "llm_model": "gemma4:e4b",
    "llm_url": "http://127.0.0.1:11434",
    "llm_timeout": 6.0,
    "llm_style": "clean",  # clean | email | chat | code
    "llm_target_lang": "español",
    "numbers_to_digits": False,  # true: "tres coma catorce" -> 3,14 (opinional, ver README)
    "streaming": True,  # dictados largos: confirma ventanas y solo transcribe la cola
    "stream_window": 12.0,  # segundos por ventana confirmada
    "mic": None,  # nombre del micro (substring); None = default del sistema
    "auto_copy": True,
    # push-to-talk: mantener hold_key graba, soltar transcribe (requiere evdev)
    "push_to_talk": False,
    "hold_key": "super+f",
    "hold_min_ms": 200,  # por debajo se considera tap (primer toggle)
    "hold_devices": [],  # nombres (substring) de teclados; [] = todos
    # OSD: auto = GTK+layer-shell si hay Wayland, si no Tk (XWayland)
    "osd_backend": "auto",
    "osd_margin_top": 80,
    "osd_monitor": "",  # nombre/índice del monitor (GTK); vacío = compositor
}

# Paths por defecto de vocabulario/correcciones (XDG)
def _default_vocab_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME", "~/.config")
    return Path(base).expanduser() / "local-stt" / "vocabulary.txt"


def _default_corrections_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME", "~/.config")
    return Path(base).expanduser() / "local-stt" / "corrections.txt"


def _resolve_vocab(name: str) -> Path:
    """Nombres relativos se resuelven contra ~/.config/local-stt/."""
    p = Path(name).expanduser()
    return p if p.is_absolute() else _default_corrections_path().parent / p

# Claves aceptadas en el TOML (todo lo demás se ignora)
_TOML_KEYS = set(_ENV_MAP) | {"sample_rate", "auto_copy", "app_vocab"}


@dataclass(frozen=True)
class Config:
    """Config con prioridad: CLI > env > ~/.config/local-stt/config.toml > defaults."""

    model: str = "large-v3-turbo"
    language: str | None = "es"
    device: str = "cuda"
    compute_type: str = "float16"
    sample_rate: int = 16000
    beam_size: int = 5
    max_record_seconds: int = 120
    auto_paste: bool = True
    auto_copy: bool = True
    dictation_commands: bool = True
    silence_stop: bool = False
    silence_rms: float = 0.008
    silence_threshold_ms: int = 1500
    vad_filter: bool = True
    overlay: bool = True
    partial_results: bool = True
    partial_interval: float = 1.5
    wake_word: bool = False
    wake_word_model: str = "hey_jarvis"
    wake_word_threshold: float = 0.5
    wake_word_engine: str = "openwakeword"  # openwakeword | vosk
    wake_word_phrase: str = "dev paul"  # frase para vosk
    vosk_model_path: str = ""  # vacío = autodetecta vosk-model-*
    post_process: str = "off"  # off | format | translate (LLM local)
    llm_model: str = "gemma4:e4b"
    llm_url: str = "http://127.0.0.1:11434"
    llm_timeout: float = 6.0
    llm_style: str = "clean"  # clean | email | chat | code
    llm_target_lang: str = "español"
    numbers_to_digits: bool = False
    streaming: bool = True  # dictados largos: confirma ventanas, al parar solo transcribe la cola
    stream_window: float = 12.0
    mic: str | None = None  # substring del nombre del micro; None = default
    # push-to-talk: mantener hold_key graba; soltar transcribe (extra [hold])
    push_to_talk: bool = False
    hold_key: str = "super+f"
    hold_min_ms: int = 200
    hold_devices: list[str] = field(default_factory=list)
    # OSD: auto = GTK+layer-shell en Wayland; tk = XWayland
    osd_backend: str = "auto"
    osd_margin_top: int = 80
    osd_monitor: str = ""  # nombre o índice (GTK); vacío = decide el compositor
    # {regex de ventana: archivo de vocabulario} — vocabulario contextual por app
    app_vocab: dict[str, str] = field(default_factory=dict)
    vocabulary_file: Path = _default_vocab_path()
    corrections_file: Path = _default_corrections_path()
    socket_path: Path = Path(os.environ.get("LOCAL_STT_SOCKET", "/tmp/local-stt.sock"))
    pid_path: Path = Path(os.environ.get("LOCAL_STT_PID", "/tmp/local-stt.pid"))
    history_path: Path = default_history_path()
    config_path: Path = default_config_path()
    log_dir: Path = default_log_dir()

    @classmethod
    def load(cls, config_file: Path | None = None, **overrides) -> "Config":
        data: dict = dict(_DEFAULTS)
        cfg_file = config_file or default_config_path()
        if tomllib is not None and cfg_file.exists():
            data.update({k: v for k, v in tomllib.loads(cfg_file.read_text()).items() if k in _TOML_KEYS})
        _apply_env(data)
        data.update({k: v for k, v in overrides.items() if v is not None})
        # Paths desde TOML llegan como str: normalizar
        for key in ("vocabulary_file", "corrections_file"):
            if key in data and data[key] is not None:
                data[key] = Path(data[key]).expanduser()
        devices = data.get("hold_devices")
        if isinstance(devices, str):
            devices = devices.split(",")
        # TOML puede traer números/None: se normaliza a lista de nombres.
        data["hold_devices"] = [str(d).strip() for d in (devices or []) if str(d).strip()]
        try:
            hold_min = int(data.get("hold_min_ms", 200))
            data["hold_min_ms"] = hold_min if hold_min >= 0 else 200
        except (TypeError, ValueError):
            data["hold_min_ms"] = 200
        try:
            data["osd_margin_top"] = max(0, int(data.get("osd_margin_top", 80)))
        except (TypeError, ValueError):
            data["osd_margin_top"] = 80
        for key in ("hold_key", "osd_backend", "osd_monitor"):
            if data.get(key) is not None:
                data[key] = str(data[key])
        if data.get("osd_backend") not in ("auto", "gtk", "tk"):
            data["osd_backend"] = "auto"
        for key in ("wake_word_engine", "wake_word_phrase", "vosk_model_path"):
            if data.get(key) is not None:
                data[key] = str(data[key])
        if data.get("wake_word_engine") not in ("openwakeword", "vosk"):
            data["wake_word_engine"] = "openwakeword"
        for key in ("post_process", "llm_model", "llm_url", "llm_style", "llm_target_lang"):
            if data.get(key) is not None:
                data[key] = str(data[key])
        if data.get("post_process") not in ("off", "format", "translate"):
            data["post_process"] = "off"
        if data.get("llm_style") not in ("clean", "email", "chat", "code"):
            data["llm_style"] = "clean"
        try:
            data["llm_timeout"] = max(0.5, float(data.get("llm_timeout", 6.0)))
        except (TypeError, ValueError):
            data["llm_timeout"] = 6.0
        return cls(**{k: v for k, v in data.items() if k in {f.name for f in fields(cls)}})


# Claves de texto plano (evita que caigan en la rama bool del parser de env)
_STR_KEYS = {
    "language", "model", "device", "compute_type", "mic", "wake_word_model",
    "hold_key", "osd_backend", "osd_monitor", "wake_word_engine", "wake_word_phrase",
    "vosk_model_path", "post_process", "llm_model", "llm_url", "llm_style",
    "llm_target_lang",
}


def _apply_env(data: dict) -> None:
    for key, env in _ENV_MAP.items():
        if env not in os.environ:
            continue
        raw = os.environ[env]
        if key in _STR_KEYS:
            data[key] = None if key == "language" and raw == "auto" else raw
        elif key in ("beam_size", "max_record_seconds", "silence_threshold_ms"):
            data[key] = int(raw)
        elif key == "osd_margin_top":
            data[key] = max(0, int(raw))
        elif key == "hold_min_ms":
            value = int(raw)
            data[key] = value if value >= 0 else 200
        elif key == "hold_devices":
            data[key] = [d.strip() for d in raw.split(",") if d.strip()]
        elif key == "silence_rms":
            data[key] = float(raw)
        elif key == "partial_interval":
            data[key] = float(raw)
        elif key == "wake_word_threshold":
            data[key] = float(raw)
        elif key == "stream_window":
            data[key] = float(raw)
        elif key == "llm_timeout":
            data[key] = max(0.5, float(raw))
        elif key in ("vocabulary_file", "corrections_file"):
            data[key] = Path(raw).expanduser()
        else:  # bools
            data[key] = raw.lower() in ("1", "true", "yes", "on")
