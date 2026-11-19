# Diseño — OSD nativo Wayland

Fase 3. Implementa `requirements.md` con el enfoque recomendado en
`research-report.md`.

## 1. Arquitectura

```
 daemon._start_recording()
   │
   ├─ select_backend(config)  ── cacheado por daemon
   │     ├─ "gtk": /usr/bin/python3 <pkg>/osd_gtk.py <socket>
   │     └─ "tk" : sys.executable -m local_speech_to_text.osd <socket>
   │
   └─ hilo vigilante (0,6 s): si GTK murió → relanza Tk una vez

 osd_gtk.py (script autocontenido)          osd.py (Tk, actual)
   stdlib a nivel de módulo                    igual que hoy
   gi/Gtk4LayerShell solo en main()
   └─ socket `level` @10 Hz → barra/texto
```

Sin IPC nuevo: el protocolo `level` (`recording`, `elapsed`, `rms`,
`partial`, `hold`) ya existe y se mantiene.

### Ficheros

| Fichero | Responsabilidad |
|---|---|
| `osd_backend.py` (nuevo) | `query_level`, `bar_fraction`, `format_status`, `should_exit`, `choose_backend`, `select_backend`, `gtk_layer_available` — todo stdlib y testeable sin GTK |
| `osd_gtk.py` (nuevo) | UI GTK4 + layer-shell; importa `gi` solo dentro de `main()`; puede ejecutarse por ruta con el python del sistema |
| `osd.py` | se queda como backend Tk; reexporta `query_level` desde `osd_backend` para no romper tests/imports |
| `daemon.py` | elige backend, lanza el argv correcto, vigilante de fallback |
| `config.py`, `config_tui.py` | `osd_backend`, `osd_margin_top` |
| `cli.py` (`doctor`) | backend elegido + motivo |

`osd_gtk.py` ejecutado como archivo añade su directorio a `sys.path`, así que
`from osd_backend import …` funciona tanto en el repo como instalado por
pacman; no importa `local_speech_to_text`.

## 2. Configuración

```toml
overlay = true              # ya existe
osd_backend = "auto"        # auto | gtk | tk
osd_margin_top = 80         # píxeles desde el borde superior
```

Env: `LOCAL_STT_OSD_BACKEND`, `LOCAL_STT_OSD_MARGIN`.

## 3. Selección de backend

```python
choose_backend(session_type, wayland_display, probe_ok, forced="auto"):
    forced == "gtk" → "gtk"
    forced == "tk"  → "tk"
    auto            → "gtk" si session_type=="wayland" and wayland_display and probe_ok
                      si no, "tk"
```

`probe_ok` = `gtk_layer_available()` ejecuta una vez, con timeout 3 s:

```
/usr/bin/python3 -c "import gi; gi.require_version('Gtk','4.0'); \
  gi.require_version('Gtk4LayerShell','1.0'); from gi.repository import Gtk, Gtk4LayerShell"
```

`select_backend` devuelve `(backend, motivo)` para logs y `doctor`; el daemon lo
cachea (`self._osd_choice`) porque el sondeo cuesta ~50-150 ms.

## 4. OSD GTK

- `Gtk.Window` + `Gtk4LayerShell.init_for_window`.
- `set_namespace("local-stt")`, `set_layer(WINDOW_LAYER_OVERLAY)`,
  `set_anchor(TOP|LEFT|RIGHT)`, `set_margin(TOP, margin)`,
  `set_exclusive_zone(-1)`, `set_keyboard_mode(KEYBOARD_MODE_NONE)`.
- Ventana transparente; tarjeta interior de ancho 420 centrada (`Gtk.Box` con
  espaciadores); CSS: fondo `rgba(26,26,46,.92)`, `border-radius: 12px`.
- Contenido: `Gtk.ProgressBar` (fracción `rms/0.15`, color verde si
  `rms ≥ 0.008`) + etiqueta `[12s]  <parcial>` + título corto.
- Timer `GLib.timeout_add(100, tick)`; `tick` consulta el socket y hace
  `Gtk.main_quit()` si `should_exit(info)`.
- `SIGTERM`/`SIGINT` → quit limpio.
- `--check`: importa gi/layer-shell y sale 0/3 sin abrir ventana (lo usa el
  sondeo y los tests).

## 5. Ciclo de vida y fallback

- `_launch_osd()` crea el proceso con `start_new_session=True` (igual que hoy).
- Hilo vigilante: espera 0,6 s; si `proc.poll()` no es `None` (murió) y el
  backend era GTK, lanza Tk una vez y actualiza `self._osd_backend_used`.
- `_kill_osd()`: `terminate()`, `wait(timeout=1)`, `kill()` si no muere.
- Si `overlay=false`, no se lanza nada (comportamiento actual).

## 6. Diagnóstico

`doctor` añade una línea **informativa** (no fallo):

```
OSD backend     gtk-layer (wayland-1, layer_shell v5)   ó
                tk (fallback: falta gtk4-layer-shell)
```

Si `osd_backend = "gtk"` forzado y el sondeo falla → `warn` con el motivo.

## 7. Trade-offs

| Decisión | A favor | En contra |
|---|---|---|
| GTK4 + layer-shell | nativo, posición exacta, sin XWayland | 3 paquetes opcionales; GNOME no lo soporta |
| Script autocontenido con python del sistema | funciona en venv sin instalar PyGObject | duplica `query_level` (~15 líneas) |
| Fallback automático a Tk | nunca te deja sin OSD | dos rutas visuales que probar |
| Sondeo cacheado | arranque de grabación sin coste | un fallback que cambia en runtime requiere reload |
| `overlay`/estructura actual intactos | riesgo bajo | no unifica ambos backends en una clase |

Alternativas descartadas: Qt6+LayerShellQt (peso), GTK toplevel sin layer-shell
(no se puede posicionar en Wayland), extensión GNOME (dos implementaciones).

## 8. Plan de pruebas

| Nivel | Qué | Requisitos |
|---|---|---|
| Unitario | `choose_backend` (matriz completa, overrides) | RF-1…3 |
| Unitario | `bar_fraction`, `format_status` (recorte 90), `should_exit` | RF-6, RF-7 |
| Unitario | `gtk_layer_available` con `/bin/true` y `/bin/false` (sin gi) | RF-1, RF-8 |
| Unitario | `osd_gtk` importable sin `gi`; `--check` sale 3 | RF-9 |
| Unitario | `_launch_osd`: argv GTK vs Tk; fallback si `poll()!=None` | RF-2, RF-8 |
| Manual | KDE Wayland: capa overlay, sin foco (`wtype`), multi-monitor | RF-4, RF-5, RNF-3 |
| Manual | GNOME Wayland y X11: Tk, sin errores en log | RF-2, RNF-3 |

CI no instala GTK: todo lo anterior salvo los manuales corre sin `gi`.

## 9. Despliegue

1. `osd_backend.py` + tests (sin tocar comportamiento).
2. `osd_gtk.py` + `--check`.
3. Integración en daemon con fallback; `overlay=true` sigue usando Tk hasta
   que el sondeo pase.
4. `doctor`, TUI y README (requisitos y optdeps).
5. AUR: `gtk4`, `python-gobject`, `gtk4-layer-shell` en `optdepends`.
