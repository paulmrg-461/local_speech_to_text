"""OSD flotante de dictado: nivel de voz + estado + texto parcial en vivo.

Tkinter (stdlib, corre vía XWayland en Wayland). Lo lanza el daemon como
subproceso al empezar a grabar y lo mata al parar. Se comunica con el daemon
consultando el socket (`level`) ~10 veces/seg.
"""

from __future__ import annotations

import json
import socket
import sys
import time


def query_level(sock_path: str, timeout: float = 0.5) -> dict | None:
    """Pregunta al daemon: {recording, elapsed, rms, partial}."""
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


class Overlay:
    W, H = 420, 72
    BAR_MAX = 0.15  # RMS que llena la barra

    def __init__(self, sock_path: str):
        import tkinter as tk

        self.sock_path = sock_path
        self.tk = tk
        self.root = tk.Tk()
        self.root.title("local-stt")
        self.root.overrideredirect(True)  # sin decoraciones
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-type", "notification")  # Wayland: capa notificación
        except tk.TclError:
            pass
        sw = self.root.winfo_screenwidth()
        x = (sw - self.W) // 2
        self.root.geometry(f"{self.W}x{self.H}+{x}+80")
        self.root.configure(bg="#1a1a2e")

        tk.Label(self.root, text="🎤 ESCUCHANDO  ·  Win+F para terminar", fg="#e0e0e0",
                 bg="#1a1a2e", font=("Sans", 10, "bold")).pack(pady=(6, 0))
        bar_bg = tk.Canvas(self.root, width=self.W - 40, height=12, bg="#2a2a4a",
                           highlightthickness=0)
        bar_bg.pack(pady=4)
        self.bar = bar_bg.create_rectangle(0, 0, 0, 12, fill="#00c853", width=0)
        self.bar_cv = bar_bg
        self.status = tk.Label(self.root, text="", fg="#9e9ec4", bg="#1a1a2e",
                               font=("Sans", 8), wraplength=self.W - 24)
        self.status.pack(fill="x")

    def _tick(self) -> None:
        info = query_level(self.sock_path)
        if info is None or not info.get("recording"):
            self.root.destroy()
            return
        frac = min(1.0, info.get("rms", 0.0) / self.BAR_MAX)
        w = int(frac * (self.W - 40))
        self.bar_cv.itemconfigure(self.bar, width=w)
        color = "#00c853" if info.get("rms", 0) >= 0.008 else "#5c6bc0"
        self.bar_cv.itemconfigure(self.bar, fill=color)
        secs = info.get("elapsed", 0)
        partial = (info.get("partial") or "").replace("\n", " ")
        self.status.configure(text=f"[{secs:4.0f}s]  {partial[-90:]}")
        self.root.after(100, self._tick)

    def run(self) -> None:
        self.root.after(100, self._tick)
        self.root.mainloop()


def main() -> None:
    sock = sys.argv[1] if len(sys.argv) > 1 else "/tmp/local-stt.sock"
    try:
        Overlay(sock).run()
    except Exception as e:
        print(f"[osd] no disponible: {e}", file=sys.stderr)
        # sin overlay no pasa nada: espera a que acabe la grabación y sale limpio
        info = query_level(sock)
        while info and info.get("recording"):
            time.sleep(0.5)
            info = query_level(sock)


if __name__ == "__main__":
    main()
