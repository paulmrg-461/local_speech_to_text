from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    # faster-whisper model: tiny, base, small, medium, large-v3, large-v3-turbo, distil-large-v3
    # Para RTX 5070 12GB: large-v3-turbo es el sweet spot (6x más rápido que large-v3, casi igual de preciso)
    model: str = os.environ.get("LOCAL_STT_MODEL", "large-v3-turbo")
    language: str | None = os.environ.get("LOCAL_STT_LANG", "es")  # None = autodetect
    device: str = os.environ.get("LOCAL_STT_DEVICE", "cuda")  # cuda | cpu
    compute_type: str = os.environ.get("LOCAL_STT_COMPUTE", "float16")  # float16, int8_float16, float32
    sample_rate: int = 16000
    silence_threshold_ms: int = int(os.environ.get("LOCAL_STT_SILENCE_MS", "1200"))
    max_record_seconds: int = int(os.environ.get("LOCAL_STT_MAX_SECS", "120"))
    beam_size: int = 5
    vad_filter: bool = True
    auto_paste: bool = os.environ.get("LOCAL_STT_AUTO_PASTE", "1") == "1"
    auto_copy: bool = True
    socket_path: Path = Path(os.environ.get("LOCAL_STT_SOCKET", "/tmp/local-stt.sock"))
    pid_path: Path = Path(os.environ.get("LOCAL_STT_PID", "/tmp/local-stt.pid"))
    # Para Wayland: wl-copy + wtype/ydotool. Para X11: xclip + xdotool
    tmp_dir: Path = Path("/tmp")
