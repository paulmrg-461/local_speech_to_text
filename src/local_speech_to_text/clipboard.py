from __future__ import annotations

import os
import shutil
import subprocess
import time


def _run(cmd: list[str], input_text: str | None = None, timeout: float = 2.0) -> bool:
    """Ejecuta un comando esperando éxito.

    IMPORTANTE: stdout/stderr a DEVNULL. wl-copy hace fork para servir el
    clipboard en background; si hereda un PIPE, communicate() espera EOF
    del hijo eternamente (2s de timeout por cada copy). Con DEVNULL el
    hijo no bloquea nada.
    """
    try:
        result = subprocess.run(
            cmd,
            input=input_text.encode("utf-8") if input_text is not None else None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
        return result.returncode == 0
    except Exception:
        return False


def _read_clipboard(timeout: float = 1.0) -> str | None:
    """Lee el portapapeles para verificación (wl-paste > xclip > xsel)."""
    for cmd in (["wl-paste", "--no-newline"], ["xclip", "-o", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--output"]):
        if not shutil.which(cmd[0]):
            continue
        try:
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
            if r.returncode == 0:
                return r.stdout.decode("utf-8", errors="replace")
        except Exception:
            continue
    # 4) pyperclip (si no hay herramientas CLI)
    try:
        import pyperclip

        return pyperclip.paste()
    except Exception:
        return None


def _clipboard_matches(expected: str, readback: str | None) -> bool:
    """Compara ignorando saltos de línea finales (wl-copy añade uno)."""
    return readback is not None and readback.rstrip("\n") == expected.rstrip("\n")


def copy_to_clipboard(text: str, verify: bool = True) -> bool:
    """Copia al portapapeles y (por defecto) verifica leyéndolo de vuelta.

    Orden: wl-copy (Wayland) → xclip → xsel → pyperclip. Con verify=True
    reintenta una vez si la lectura no coincide y retorna False si fracasa.
    """
    if not text:
        return False

    for attempt in (1, 2) if verify else (1,):
        ok = _copy_once(text)
        if not ok:
            continue
        if not verify or _clipboard_matches(text, _read_clipboard()):
            return True
        print(f"[clipboard] verificación falló (intento {attempt}/2), reintentando")

    print("[clipboard] fallo: el texto no llegó al portapapeles")
    return False


def _copy_once(text: str) -> bool:
    """Una pasada de copia con el primer backend disponible."""
    # 1) Wayland nativo
    if shutil.which("wl-copy"):
        if _run(["wl-copy"], input_text=text):
            # también copiar a primary si existe
            _run(["wl-copy", "--primary"], input_text=text)
            print("[clipboard] wl-copy OK")
            return True

    # 2) X11
    if shutil.which("xclip"):
        if _run(["xclip", "-selection", "clipboard"], input_text=text):
            _run(["xclip", "-selection", "primary"], input_text=text)
            print("[clipboard] xclip OK")
            return True

    if shutil.which("xsel"):
        if _run(["xsel", "--clipboard", "--input"], input_text=text):
            print("[clipboard] xsel OK")
            return True

    # 3) pyperclip fallback
    try:
        import pyperclip

        pyperclip.copy(text)
        print("[clipboard] pyperclip OK")
        return True
    except Exception as e:
        print(f"[clipboard] fallaron todos los métodos: {e}")
        return False


def paste_via_key() -> bool:
    """Simula Ctrl+V. Wayland: wtype/ydotool. X11: xdotool. Retorna si se lanzó."""
    # Pequeña pausa para que el clipboard se asiente (Wayland es asíncrono)
    time.sleep(0.12)

    # wtype es el más fiable en Wayland (GNOME/KDE con xdg-portal)
    if shutil.which("wtype"):
        # wtype no simula Ctrl+V sino que escribe; mejor simular Ctrl+V si es posible
        # Pero wtype puede enviar ctrl+v con: wtype -M ctrl -P v -m ctrl
        # probamos ambos: primero ctrl+v, fallback a escribir? No, queremos pegar.
        if _run(["wtype", "-M", "ctrl", "-k", "v", "-m", "ctrl"]):
            print("[paste] wtype Ctrl+V")
            return True
        # fallback: si no, wtype no disponible para ctrl, intentar ydotool
    if shutil.which("ydotool"):
        # ydotool necesita daemon ydotoold
        if _run(["ydotool", "key", "29:1", "47:1", "47:0", "29:0"]):  # ctrl+v
            print("[paste] ydotool Ctrl+V")
            return True
    if shutil.which("xdotool"):
        # Solo funciona en X11 o XWayland con foco XWayland
        if _run(["xdotool", "key", "ctrl+v"]):
            print("[paste] xdotool Ctrl+V")
            return True

    # Sin herramienta de paste, el usuario hace Ctrl+V manual
    print("[paste] no hay herramienta de auto-paste instalada (instala wtype o ydotool)")
    return False


def notify(title: str, body: str, urgency: str = "normal", icon: str | None = None) -> None:
    if not shutil.which("notify-send"):
        print(f"[notify] {title}: {body}")
        return
    cmd = ["notify-send", "-u", urgency, "-t", "3000", title, body]
    if icon:
        cmd.extend(["-i", icon])
    _run(cmd)


def play_sound(kind: str = "start") -> None:
    """Beep opcional al iniciar/parar. No falla si no hay canberra."""
    if shutil.which("canberra-gtk-play"):
        snd = "message" if kind == "start" else "complete"
        _run(["canberra-gtk-play", "-i", snd], timeout=1.0)
    elif shutil.which("paplay"):
        # fallback sin sonido, solo log
        pass
