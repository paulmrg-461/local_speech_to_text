"""OSD flotante de dictado: nivel de voz + estado + texto parcial en vivo.

Tkinter (stdlib, corre vía XWayland en Wayland). Lo lanza el daemon como
subproceso al empezar a grabar y lo mata al parar. Se comunica con el daemon
consultando el socket (`level`) ~10 veces/seg.
"""

from __future__ import annotations

import sys
import time

from .osd_backend import bar_fraction, format_status, query_level, should_exit

__all__ = ["Overlay", "query_level", "main"]


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
        if should_exit(info):
            self.root.destroy()
            return
        rms = info.get("rms", 0.0)
        self.bar_cv.itemconfigure(self.bar, width=int(bar_fraction(rms, self.BAR_MAX) * (self.W - 40)))
        color = "#00c853" if rms >= 0.008 else "#5c6bc0"
        self.bar_cv.itemconfigure(self.bar, fill=color)
        self.status.configure(text=format_status(info))
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
