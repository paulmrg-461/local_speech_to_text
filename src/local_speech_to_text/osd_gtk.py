#!/usr/bin/env python3
"""OSD nativo Wayland: GTK4 + gtk4-layer-shell (script autocontenido).

Se ejecuta **por ruta** con el python del sistema, que es el que ve PyGObject:

    /usr/bin/python3 /ruta/osd_gtk.py /tmp/local-stt.sock --margin 80

A nivel de módulo solo se importa stdlib (CI y venv sin `gi` pueden importarlo
y testear la lógica). `gi` se importa dentro de `check()`/`run()`.

Diseño: docs/specs/osd-wayland/design.md
"""

from __future__ import annotations

import signal
import sys
import time

try:  # importado como paquete (tests) o como script (daemon)
    from .osd_backend import (
        bar_fraction,
        format_status,
        preview_info,
        query_level,
        should_exit,
    )
except ImportError:  # pragma: no cover - ejecución por ruta
    from osd_backend import bar_fraction, format_status, preview_info, query_level, should_exit

DEFAULT_SOCK = "/tmp/local-stt.sock"
DEFAULT_MARGIN = 80
DEFAULT_PREVIEW = 6.0
WIDTH = 420
TICK_MS = 100

CSS = b"""
window { background: transparent; }
.osd {
  background: rgba(26, 26, 46, 0.92);
  border-radius: 12px;
  padding: 8px 14px;
}
.osd-title { color: #e0e0e0; font-weight: bold; font-size: 10pt; }
.osd-status { color: #9e9ec4; font-size: 8pt; }
progressbar > trough { background: #2a2a4a; border-radius: 4px; min-height: 10px; }
progressbar > trough > progress { background: #5c6bc0; border-radius: 4px; min-height: 10px; }
progressbar.loud > trough > progress { background: #00c853; }
"""


def check() -> bool:
    """True si este intérprete puede usar GTK4 + layer-shell."""
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Gdk", "4.0")
        gi.require_version("Gtk4LayerShell", "1.0")
        from gi.repository import Gtk, Gtk4LayerShell  # noqa: F401

        return True
    except Exception:
        return False


def parse_args(argv: list[str]) -> tuple[str, int, float | None]:
    """(socket, margen, segundos de preview) desde argv; `--check` va antes."""
    args = [a for a in argv if a != "--check"]
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


def run(sock: str, margin: int = DEFAULT_MARGIN, preview: float | None = None) -> None:
    """Ventana layer-shell que se refresca a 10 Hz hasta que pare la grabación."""
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gdk, GLib, Gtk, Gtk4LayerShell, Pango

    Gtk.init()
    if not Gtk4LayerShell.is_supported():
        raise RuntimeError(
            "layer-shell no soportado: compositor sin wlr-layer-shell o falta LD_PRELOAD "
            "(el daemon lo añade solo; ejecuta vía 'local-stt osd --preview')"
        )

    app = Gtk.Application(application_id="io.github.paulmrg461.LocalSttOsd")
    started = time.monotonic()

    def activate(application: Gtk.Application) -> None:
        win = Gtk.ApplicationWindow(application=application)
        win.add_css_class("osd-window")
        win.set_can_focus(False)

        Gtk4LayerShell.init_for_window(win)
        Gtk4LayerShell.set_namespace(win, "local-stt")
        Gtk4LayerShell.set_layer(win, Gtk4LayerShell.Layer.OVERLAY)
        for edge in (Gtk4LayerShell.Edge.TOP, Gtk4LayerShell.Edge.LEFT, Gtk4LayerShell.Edge.RIGHT):
            Gtk4LayerShell.set_anchor(win, edge, True)
        Gtk4LayerShell.set_margin(win, Gtk4LayerShell.Edge.TOP, margin)
        Gtk4LayerShell.set_exclusive_zone(win, -1)
        # Nunca robar el teclado: lo que se escriba va a la app activa.
        Gtk4LayerShell.set_keyboard_mode(win, Gtk4LayerShell.KeyboardMode.NONE)

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.add_css_class("osd")
        card.set_size_request(WIDTH, -1)

        title = Gtk.Label(label="🎤 ESCUCHANDO  ·  Win+F para terminar")
        title.add_css_class("osd-title")
        bar = Gtk.ProgressBar()
        bar.set_show_text(False)
        status = Gtk.Label(label="")
        status.add_css_class("osd-status")
        status.set_xalign(0.0)
        status.set_ellipsize(Pango.EllipsizeMode.END)
        card.append(title)
        card.append(bar)
        card.append(status)

        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        outer.set_halign(Gtk.Align.CENTER)
        outer.append(card)
        win.set_child(outer)
        win.present()

        def tick() -> bool:
            if preview is not None:
                elapsed = time.monotonic() - started
                if elapsed > preview:
                    application.quit()
                    return False
                info = preview_info(elapsed)
            else:
                info = query_level(sock)
                if should_exit(info):
                    application.quit()
                    return False
            rms = float(info.get("rms") or 0.0)
            bar.set_fraction(bar_fraction(rms))
            if rms >= 0.008:
                bar.add_css_class("loud")
            else:
                bar.remove_css_class("loud")
            status.set_text(format_status(info))
            return True

        GLib.timeout_add(TICK_MS, tick)

    app.connect("activate", activate)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: app.quit())
    app.run([])


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--check" in argv:
        raise SystemExit(0 if check() else 3)
    sock, margin, preview = parse_args(argv)
    try:
        run(sock, margin, preview)
    except Exception as e:  # sin display, typelib roto, compositor sin layer-shell
        print(f"[osd] GTK no disponible: {e}", file=sys.stderr)
        raise SystemExit(2) from e


if __name__ == "__main__":
    main()
