"""Lógica del OSD sin dependencias de UI: socket, formato y elección de backend.

`osd_gtk.py` (backend Wayland) y `osd.py` (Tk) comparten estas funciones. Todo
aquí es stdlib: se puede importar y testear sin GTK ni Tk.
"""

from __future__ import annotations

import ctypes.util
import json
import math
import os
import shutil
import socket
import subprocess
from pathlib import Path

# Sondeo de layer-shell con el python del sistema (el venv no ve PyGObject).
# `is_supported()` es False si el compositor no expone wlr-layer-shell o si
# gtk4-layer-shell se cargó después de libwayland (el caso de Arch sin preload).
GTK_PROBE = (
    "import gi;"
    "gi.require_version('Gtk','4.0');"
    "gi.require_version('Gdk','4.0');"
    "gi.require_version('Gtk4LayerShell','1.0');"
    "from gi.repository import Gtk, Gtk4LayerShell;"
    "Gtk.init();"
    "raise SystemExit(0 if Gtk4LayerShell.is_supported() else 1)"
)

_PRELOAD_PATHS = (
    "/usr/lib/libgtk4-layer-shell.so.0",
    "/usr/lib/libgtk4-layer-shell.so",
)


def layer_shell_preload() -> str | None:
    """Biblioteca a precargar para que layer-shell inicialice.

    En Arch, PyGObject enlaza libwayland antes que gtk4-layer-shell y la capa
    falla con "Failed to initialize layer surface". `LD_PRELOAD` con el soname
    resuelve el orden de símbolos sin recompilar.
    """
    soname = ctypes.util.find_library("gtk4-layer-shell")
    if soname:
        return soname
    for path in _PRELOAD_PATHS:
        if Path(path).exists():
            return path
    return None


def probe_env(base: dict | None = None) -> dict:
    """Entorno para el OSD/probe GTK con LD_PRELOAD ya aplicado."""
    env = dict(os.environ if base is None else base)
    preload = layer_shell_preload()
    if preload:
        current = env.get("LD_PRELOAD")
        env["LD_PRELOAD"] = f"{preload}:{current}" if current else preload
    return env


def query_level(sock_path: str, timeout: float = 0.5) -> dict | None:
    """Pregunta al daemon: {recording, elapsed, rms, partial, hold}."""
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(sock_path)
        s.sendall(b"level\n")
        resp = s.recv(4096).decode().strip()
        s.close()
        return json.loads(resp) if resp.startswith("{") else None
    except Exception:
        return None


def bar_fraction(rms: float, full_scale: float = 0.15) -> float:
    """RMS -> fracción 0..1 de la barra (0.15 llena el ancho, igual que el Tk)."""
    if full_scale <= 0:
        return 0.0
    return max(0.0, min(1.0, float(rms) / full_scale))


def format_status(info: dict) -> str:
    """`[12s]  texto parcial` recortado a los últimos 90 caracteres."""
    secs = info.get("elapsed") or 0
    partial = (info.get("partial") or "").replace("\n", " ")
    return f"[{secs:4.0f}s]  {partial[-90:]}"


def should_exit(info: dict | None) -> bool:
    """El OSD se cierra si el daemon no responde o ya no graba."""
    return info is None or not info.get("recording")


def title_text(hold: bool) -> str:
    """Instrucción del OSD según el modo (mantener vs pulsar)."""
    if hold:
        return "🎤 ESCUCHANDO  ·  suelta la tecla para terminar"
    return "🎤 ESCUCHANDO  ·  Win+F para terminar"


def preview_info(elapsed: float) -> dict:
    """Datos sintéticos para `--preview`: mismo contrato que el socket."""
    rms = 0.06 + 0.05 * abs(math.sin(elapsed * 2.0))
    return {
        "recording": True,
        "elapsed": elapsed,
        "rms": round(rms, 4),
        "partial": "Vista previa del OSD · así se verá mientras dictas",
    }


def find_system_python() -> str | None:
    """Python del sistema (con PyGObject/GTK), no el del venv."""
    for candidate in ("/usr/bin/python3", shutil.which("python3")):
        if candidate and Path(candidate).exists():
            return candidate
    return None


def gtk_layer_available(
    python: str | None = None,
    timeout: float = 3.0,
    env: dict | None = None,
) -> bool:
    """True si ese python puede importar GTK4 + gtk4-layer-shell."""
    py = python or find_system_python()
    if not py:
        return False
    try:
        proc = subprocess.run(
            [py, "-c", GTK_PROBE],
            capture_output=True,
            timeout=timeout,
            env=probe_env(env),
        )
        return proc.returncode == 0
    except Exception:
        return False


def choose_backend(
    session_type: str | None,
    wayland_display: str | None,
    probe_ok: bool,
    forced: str = "auto",
) -> str:
    """`gtk` solo en Wayland con sondeo positivo; override explícito gana."""
    forced = (forced or "auto").lower()
    if forced in ("gtk", "tk"):
        return forced
    if session_type == "wayland" and wayland_display and probe_ok:
        return "gtk"
    return "tk"


def select_backend(
    forced: str = "auto",
    env: dict | None = None,
    probe: bool | None = None,
) -> tuple[str, str]:
    """(backend, motivo legible) para logs y `doctor`.

    `env`/`probe` se inyectan en tests; por defecto se usa el entorno real y se
    sondea una vez con el python del sistema.
    """
    env = os.environ if env is None else env
    session = env.get("XDG_SESSION_TYPE", "")
    wayland = env.get("WAYLAND_DISPLAY", "")
    forced = (forced or "auto").lower()

    if forced in ("gtk", "tk"):
        if forced == "gtk" and not (session == "wayland" and wayland):
            return "gtk", "forzado (sin sesión Wayland: puede fallar)"
        return forced, "forzado en config"

    ok = gtk_layer_available() if probe is None else probe
    backend = choose_backend(session, wayland, ok, forced="auto")
    if backend == "gtk":
        return "gtk", f"wayland ({wayland}) + layer-shell"
    if session != "wayland":
        return "tk", f"sesión {session or 'desconocida'} (sin layer-shell)"
    if not wayland:
        return "tk", "Wayland sin WAYLAND_DISPLAY"
    return "tk", "falta gtk4-layer-shell o python-gobject"


def describe(backend: str, reason: str) -> str:
    """Texto para `doctor`/logs."""
    label = "gtk-layer" if backend == "gtk" else "tk"
    return f"{label} · {reason}"
