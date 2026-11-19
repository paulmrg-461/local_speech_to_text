# Tareas — OSD nativo Wayland

> **Estado (2026-11-19):** T1-T7 implementadas y con tests. T8 (prueba visual en
> KDE Wayland/GNOME/X11) pendiente de hardware/sesión.

Atómicas y ordenadas. Ninguna se implementa sin aprobar esta lista (fase 4).
Tests: éxito / fallo / seguridad cuando aplique.

## T1 · `osd_backend.py` puro
- Mover/copiar `query_level`, `bar_fraction`, `format_status`, `should_exit`.
- `choose_backend(session_type, wayland_display, probe_ok, forced)`.
- `osd.py` reexporta `query_level` (compatibilidad).
- Tests: matriz de backend, fracción 0/medio/tope, recorte de parcial, salida
  por `recording=false`/socket caído.

**DoD:** RF-1…3, RF-6, RF-7; sin imports de gi.

## T2 · Sondeo y `select_backend`
- `gtk_layer_available(python, timeout=3)` y `find_system_python()`
  (`/usr/bin/python3` si existe; si no, `python3` del PATH).
- `select_backend` devuelve `(backend, motivo)`.
- Tests: `/bin/true`→True, `/bin/false`→False, timeout, sin binario.

**DoD:** RF-1, RF-2, RF-8.

## T3 · `osd_gtk.py` (UI)
- stdlib a nivel de módulo; `gi`/`Gtk4LayerShell` en `main()`.
- Ventana layer-shell overlay, anclaje TOP/L/R, margen, `exclusive_zone=-1`,
  `keyboard_mode=none`; tarjeta 420 centrada, CSS, barra y parcial.
- `--check` (0 disponible / 3 no); SIGTERM limpio.
- Tests: import sin gi; `--check` en CI sin gi = 3; `format_status` compartido.

**DoD:** RF-4…7, RF-9, RS-2.

## T4 · Integración en daemon
- `select_backend` cacheado; argv según backend (python del sistema + ruta).
- Hilo vigilante de 0,6 s con fallback único a Tk.
- `_kill_osd` con terminate/wait/kill.
- Tests: argv correcto por backend; fallback con Popen falso; overlay=false no
  lanza nada.

**DoD:** RF-2, RF-8, RNF-1.

## T5 · Config y TUI
- `osd_backend` (auto/gtk/tk) y `osd_margin_top` en defaults, env y TOML.
- Menú TUI: choice + int; `_render` correcto.
- Tests: env gana, valores por defecto, round-trip TUI.

**DoD:** RNF-2.

## T6 · `doctor`
- Línea informativa con backend, motivo y sesión.
- `osd_backend="gtk"` forzado e inviable → warn accionable.
- Tests: mensaje con motivo; no incrementa fallos si Tk funciona.

**DoD:** RNF-4.

## T7 · Documentación y empaquetado
- README: sección OSD (backend, requisitos, fallback, GNOME), optdeps.
- AUR: `gtk4`, `python-gobject`, `gtk4-layer-shell` en `optdepends`.
- Captura/actualización del roadmap (partial → done en KDE/wlroots).

**DoD:** RNF-2/RNF-3 documentados.

## T8 · Prueba manual (fuera de CI)
- KDE Wayland: overlay, no roba foco (`wtype`), multi-monitor, terminar con
  Win+F y por socket.
- GNOME Wayland y X11: Tk sin errores.
- Atajo: `local-stt osd --preview --seconds 4` muestra el OSD sin dictar.
- Registrar resultados en este fichero.

**DoD:** RF-4, RF-5, RNF-3 verificados en hardware.

## Orden

```
T1 → T2 → T4 → T6 → T8
        T3 ┘
        T5 ┘
        T7
```

## Fuera de alcance

- OSD en GNOME sin layer-shell (requiere extensión Shell).
- Animaciones/transiciones del OSD.
- Selección manual de monitor (`osd_monitor`), posible en una v2.
