from __future__ import annotations

import os
import shutil
import subprocess
import time


def _run(cmd: list[str], input_text: str | None = None, timeout: float = 2.0) -> bool:
    try:
        result = subprocess.run(
            cmd,
            input=input_text.encode("utf-8") if input_text is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        return result.returncode == 0
    except Exception:
        return False


def copy_to_clipboard(text: str) -> bool:
    """Copia al portapapeles: intenta wl-copy (Wayland), luego xclip/xsel, luego pyperclip."""
    if not text:
        return False

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
        print(f"[clipboard] fallo todos los métodos: {e}")
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
