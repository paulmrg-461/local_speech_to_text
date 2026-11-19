"""OSD flotante de dictado: nivel de voz + estado + texto parcial en vivo.

Tkinter (stdlib, corre vía XWayland en Wayland). Lo lanza el daemon como
subproceso al empezar a grabar y lo mata al parar. Se comunica con el daemon
consultando el socket (`level`) ~10 veces/seg.
"""

from __future__ import annotations

import os
import sys
import time

from .osd_backend import (
    bar_fraction,
    format_status,
    preview_info,
    query_level,
    should_exit,
    title_text,
)

__all__ = ["Overlay", "parse_argv", "query_level", "main"]

DEFAULT_SOCK = "/tmp/local-stt.sock"
DEFAULT_PREVIEW = 6.0
DEFAULT_MARGIN = 80


def parse_argv(argv: list[str]) -> tuple[str, int, float | None]:
    """(socket, margen superior, segundos de preview) para el OSD Tk."""
    args = list(argv)
    sock = DEFAULT_SOCK
    margin = DEFAULT_MARGIN
    preview: float | None = None
    if "--preview" in args:
        preview = DEFAULT_PREVIEW
        args.remove("--preview")
    if "--seconds" in args:
        idx = args.index("--seconds")
        preview = float(args[idx + 1])
        del args[idx:idx + 2]
    if "--margin" in args:
        idx = args.index("--margin")
        margin = int(args[idx + 1])
        del args[idx:idx + 2]
    rest = [a for a in args if not a.startswith("--")]
    if rest:
        sock = rest[0]
    return sock, margin, preview


class Overlay:
    W, H = 420, 72
    BAR_MAX = 0.15  # RMS que llena la barra

    def __init__(self, sock_path: str, preview: float | None = None, margin: int = DEFAULT_MARGIN):
        import tkinter as tk

        self.sock_path = sock_path
        self.preview = preview
        self.margin = margin
        self._started = time.monotonic()
        self._misses = 0
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
        self.root.geometry(f"{self.W}x{self.H}+{x}+{self.margin}")
        self.root.configure(bg="#1a1a2e")

        tk.Label(self.root, text=title_text(os.environ.get("LOCAL_STT_HOLD") == "1"), fg="#e0e0e0",
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
        if self.preview is not None:
            elapsed = time.monotonic() - self._started
            if elapsed > self.preview:
                self.root.destroy()
                return
            info = preview_info(elapsed)
        else:
            info = query_level(self.sock_path)
            if info is None:
                self._misses += 1
                if self._misses < 10:  # ~1s de socket ocupado: no cerrar
                    self.root.after(100, self._tick)
                    return
                self.root.destroy()
                return
            self._misses = 0
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
    sock, margin, preview = parse_argv(sys.argv[1:])
    try:
        Overlay(sock, preview, margin).run()
    except Exception as e:
        print(f"[osd] no disponible: {e}", file=sys.stderr)
        if preview is not None:
            return
        # sin overlay no pasa nada: espera a que acabe la grabación y sale limpio
        info = query_level(sock)
        while info and info.get("recording"):
            time.sleep(0.5)
            info = query_level(sock)


if __name__ == "__main__":
    main()
