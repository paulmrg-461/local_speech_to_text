"""TUI de configuración: `local-stt config`.

Menú interactivo (stdin) para editar ~/.config/local-stt/config.toml sin
tocar el archivo a mano. Si no hay TTY, muestra la config actual y sale.
Reescribe el TOML completo desde el esquema conocido (los comentarios del
template se pierden; el resto de claves desconocidas se conservan).
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]

# (clave, prompt, tipo, opciones o None)
_MENU = [
    ("model", "Modelo", "choice",
     ["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo", "distil-large-v3"]),
    ("language", "Idioma (es/en/auto…)", "str", None),
    ("device", "Dispositivo", "choice", ["cuda", "cpu"]),
    ("compute_type", "Compute", "choice", ["float16", "int8_float16", "float32", "int8"]),
    ("beam_size", "Beam size (precisión/velocidad)", "int", None),
    ("max_record_seconds", "Auto-stop máx (segundos)", "int", None),
    ("auto_paste", "Auto-pegar Ctrl+V", "bool", None),
    ("dictation_commands", "Puntuación hablada", "bool", None),
    ("silence_stop", "Auto-stop por silencio", "bool", None),
    ("silence_threshold_ms", "Silencio para parar (ms)", "int", None),
    ("overlay", "OSD flotante", "bool", None),
    ("osd_backend", "OSD backend", "choice", ["auto", "gtk", "tk"]),
    ("osd_margin_top", "OSD margen superior (px)", "int", None),
    ("osd_monitor", "OSD monitor (nombre/índice, vacío=auto)", "str", None),
    ("partial_results", "Texto parcial en vivo", "bool", None),
    ("numbers_to_digits", "Números hablados a dígitos", "bool", None),
    ("streaming", "Streaming (dictados largos)", "bool", None),
    ("wake_word", "Wake word (hey jarvis)", "bool", None),
    ("wake_word_model", "Modelo wake word", "str", None),
    ("wake_word_engine", "Motor wake word", "choice", ["openwakeword", "vosk"]),
    ("wake_word_phrase", "Frase wake word (vosk)", "str", None),
    ("vosk_model_path", "Modelo Vosk (vacío=auto)", "str", None),
    ("post_process", "Post-proceso LLM", "choice", ["off", "format", "translate"]),
    ("llm_model", "Modelo Ollama", "str", None),
    ("llm_url", "URL de Ollama", "str", None),
    ("llm_timeout", "Timeout LLM (s)", "float", None),
    ("llm_style", "Estilo (format)", "choice", ["clean", "email", "chat", "code"]),
    ("llm_target_lang", "Idioma destino (translate)", "str", None),
    ("push_to_talk", "Push-to-talk (mantener tecla)", "bool", None),
    ("hold_key", "Tecla hold (super+f)", "str", None),
    ("hold_min_ms", "Tap mínimo para hold (ms)", "int", None),
    ("hold_devices", "Teclados para hold (coma; vacío=todos)", "list", None),
]

_ORDER = [k for k, *_ in _MENU] + [
    "stream_window", "partial_interval", "wake_word_threshold", "sample_rate",
]
_BOOL_KEYS = {k for k, _, t, _ in _MENU if t == "bool"}


def _load_current(path: Path) -> dict:
    if tomllib is not None and path.exists():
        return dict(tomllib.loads(path.read_text()))
    return {}


def _render(cfg: dict) -> str:
    lines = [
        "# Config de local-stt (el entorno LOCAL_STT_* gana sobre este archivo)",
        "# Generado por `local-stt config` — edítalo libremente.",
    ]
    for key in _ORDER:
        if key not in cfg:
            continue
        val = cfg[key]
        if isinstance(val, bool):
            lines.append(f"{key} = {'true' if val else 'false'}")
        elif isinstance(val, (int, float)):
            lines.append(f"{key} = {val}")
        elif isinstance(val, str):
            lines.append(f'{key} = "{val}"')
        elif isinstance(val, (list, tuple)):
            items = ", ".join(f'"{item}"' for item in val)
            lines.append(f"{key} = [{items}]")
    # conservar tablas desconocidas (app_vocab etc.) de forma simple
    for key, val in cfg.items():
        if key in _ORDER:
            continue
        if isinstance(val, dict):
            lines.append(f"\n[{key}]")
            for k2, v2 in val.items():
                lines.append(f'"{k2}" = "{v2}"')
        else:
            lines.append(f"# (sin soporte TUI) {key} = {val!r}")
    return "\n".join(lines) + "\n"


def _ask(label: str, kind: str, current, options: list | None):
    if kind == "bool":
        new = input(f"{label} [{'on' if current else 'off'}] (s/n, Enter=keep): ").strip().lower()
        return current if new == "" else new in ("s", "si", "sí", "y", "yes", "on", "1", "true")
    if kind == "int":
        new = input(f"{label} [{current}] (Enter=keep): ").strip()
        return current if new == "" else int(new)
    if kind == "float":
        new = input(f"{label} [{current}] (Enter=keep): ").strip()
        return current if new == "" else float(new)
    if kind == "choice":
        opts = options or []
        print(f"{label}: " + " | ".join(f"{i}:{o}" for i, o in enumerate(opts)))
        new = input(f"Elegir [actual: {current}] (número o nombre, Enter=keep): ").strip()
        if new == "":
            return current
        if new.isdigit() and int(new) < len(opts):
            return opts[int(new)]
        return new if new in opts else current
    if kind == "list":
        current_txt = ", ".join(current or [])
        new = input(f"{label} [{current_txt}] (coma, Enter=keep): ").strip()
        if new == "":
            return current
        return [item.strip() for item in new.split(",") if item.strip()]
    # str
    new = input(f"{label} [{current}] (Enter=keep): ").strip()
    return current if new == "" else new


def run_tui(config_path: Path) -> int:
    """Retorna 0 si se guardó algo, 1 si solo se mostró."""
    from .config import _DEFAULTS

    if not sys.stdin.isatty():
        cfg = _load_current(config_path)
        print(_render(cfg))
        return 1
    original = _load_current(config_path)
    new_cfg = dict(original)
    changed = False
    for key, label, kind, options in _MENU:
        had = key in original
        current = original.get(key, _DEFAULTS.get(key))
        val = _ask(label, kind, current, options)
        if val != current or (had and val != original[key]):
            # respuesta distinta al valor previo (o al default si era ausente)
            new_cfg[key] = val
            changed = True
    if not changed:
        print("\nSin cambios. Config actual:")
        print(_render(original))
        return 0
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(_render(new_cfg))
    print(f"\n✅ Guardado en {config_path}")
    print("Aplica en caliente con: local-stt reload")
    return 0
