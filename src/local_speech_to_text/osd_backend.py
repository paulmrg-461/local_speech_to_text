"""Lógica del OSD sin dependencias de UI: socket, formato y elección de backend.

`osd_gtk.py` (backend Wayland) y `osd.py` (Tk) comparten estas funciones. Todo
aquí es stdlib: se puede importar y testear sin GTK ni Tk.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
from pathlib import Path

# Sondeo de layer-shell con el python del sistema (el venv no ve PyGObject).
GTK_PROBE = (
    "import gi;"
    "gi.require_version('Gtk','4.0');"
    "gi.require_version('Gtk4LayerShell','1.0');"
    "from gi.repository import Gtk, Gtk4LayerShell"
)


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
            env=env if env is not None else os.environ.copy(),
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
