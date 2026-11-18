"""Detectar la ventana activa para elegir vocabulario contextual.

Cadena de detección (primero que funcione):
  1. kdotool (KDE Wayland, exacto: `kdotool getactivewindow getwindowname`)
  2. DBus KWin queryWindowInfo (best-effort: caption de la ventana activa)
  3. xdotool (solo X11)
Si nada funciona -> None y se usa el vocabulario por defecto.
"""

from __future__ import annotations

import re
import shutil
import subprocess


def _kdotool() -> str | None:
    if not shutil.which("kdotool"):
        return None
    try:
        r = subprocess.run(["kdotool", "getactivewindow", "getwindowname"],
                           capture_output=True, timeout=1.5)
        if r.returncode == 0:
            return r.stdout.decode("utf-8", errors="replace").strip() or None
    except Exception:
        pass
    return None


def _kwin_dbus() -> str | None:
    """Best-effort: queryWindowInfo puede pedir interacción; por eso se
    llama en segundo plano (ver daemon._apply_contextual_vocab)."""
    if not shutil.which("qdbus6"):
        return None
    try:
        r = subprocess.run(["qdbus6", "org.kde.KWin", "/KWin", "org.kde.KWin.queryWindowInfo"],
                           capture_output=True, timeout=6.0)
        if r.returncode != 0:
            return None
        for line in r.stdout.decode("utf-8", errors="replace").splitlines():
            m = re.match(r"^caption:\s*(.+)$", line.strip())
            if m and m.group(1).strip():
                return m.group(1).strip()
    except Exception:
        pass
    return None


def _xdotool() -> str | None:
    if not shutil.which("xdotool"):
        return None
    try:
        r = subprocess.run(["xdotool", "getactivewindow", "getwindowname"],
                           capture_output=True, timeout=1.0)
        if r.returncode == 0:
            return r.stdout.decode("utf-8", errors="replace").strip() or None
    except Exception:
        pass
    return None


def get_active_window_name() -> str | None:
    for detector in (_kdotool, _kwin_dbus, _xdotool):
        name = detector()
        if name:
            return name
    return None


def match_profile(window_name: str | None, profiles: dict[str, str]) -> str | None:
    """Devuelve el primer profile cuyo regex (clave) matchea el nombre de ventana."""
    if not window_name:
        return None
    for pattern, profile in profiles.items():
        try:
            if re.search(pattern, window_name, flags=re.IGNORECASE):
                return profile
        except re.error:
            continue  # patrón inválido: ignorar
    return None
