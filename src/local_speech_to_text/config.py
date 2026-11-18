from __future__ import annotations

import os
from dataclasses import dataclass, fields
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
    "auto_copy": True,
}

# Paths por defecto de vocabulario/correcciones (XDG)
def _default_vocab_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME", "~/.config")
    return Path(base).expanduser() / "local-stt" / "vocabulary.txt"


def _default_corrections_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME", "~/.config")
    return Path(base).expanduser() / "local-stt" / "corrections.txt"

# Claves aceptadas en el TOML (todo lo demás se ignora)
_TOML_KEYS = set(_ENV_MAP) | {"sample_rate", "auto_copy"}


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
        return cls(**{k: v for k, v in data.items() if k in {f.name for f in fields(cls)}})


def _apply_env(data: dict) -> None:
    for key, env in _ENV_MAP.items():
        if env not in os.environ:
            continue
        raw = os.environ[env]
        if key in ("language", "model", "device", "compute_type"):
            data[key] = None if key == "language" and raw == "auto" else raw
        elif key in ("beam_size", "max_record_seconds", "silence_threshold_ms"):
            data[key] = int(raw)
        elif key == "silence_rms":
            data[key] = float(raw)
        elif key in ("vocabulary_file", "corrections_file"):
            data[key] = Path(raw).expanduser()
        else:  # bools
            data[key] = raw.lower() in ("1", "true", "yes", "on")
