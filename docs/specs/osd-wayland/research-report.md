# Research — OSD nativo Wayland

Fecha: 2026-11-19 · Estado: cerrado (fase 1) · Autor: DevPaul

## 1. Pregunta

¿Cómo mostrar el indicador de dictado (nivel de voz + texto parcial) como una
ventana **nativa Wayland**, sin depender de XWayland, en KDE/GNOME/wlroots y
sin robar el foco del teclado?

## 2. Estado actual (evidencia)

| Hecho | Evidencia |
|---|---|
| El OSD es Tkinter | `osd.py:1-97` |
| Tk instalado es 8.6 (sin backend Wayland) | `tkinter.TkVersion == 8.6` |
| En Wayland corre vía XWayland | `DISPLAY=:1` además de `WAYLAND_DISPLAY=wayland-1` |
| Posición/topmost vía X11 | `overrideredirect`, `-topmost`, `geometry(...+80)` |
| El daemon lo lanza como subproceso y lo mata al parar | `daemon.py:_launch_osd/_kill_osd` |
| Protocolo OSD: JSON `level` por socket Unix | `osd.py:query_level`, `daemon._level_payload` |
| Limitación declarada | README roadmap: “Wayland-native OSD — partial” |

Esta máquina (KDE, sesión Wayland) expone `zwlr_layer_shell_v1` **v5**
(`wayland-info`), tiene GTK4 + PyGObject, y **no** tiene instalado
`gtk4-layer-shell` (paquete en `extra`, 1.3.0). Tk 8.6 no tiene backend
Wayland (Tk 9 lo añadió de forma experimental), así que el OSD actual siempre
pasa por XWayland.

## 3. Opciones

### A. GTK4 + `gtk4-layer-shell` (PyGObject)
- `zwlr_layer_shell_v1`: capa `overlay`, anclaje, márgenes, sin foco de teclado
  (`keyboard_mode = none`), sin reservar espacio (`exclusive_zone = -1`).
- Funciona en KWin y compositores wlroots (sway, hyprland…).
- **GNOME/Mutter no implementa layer-shell** → requiere fallback.
- Dependencias del sistema: `gtk4`, `python-gobject`, `gtk4-layer-shell`
  (las tres en `extra` en Arch). No se instala nada por pip.
- Ventaja clave: ventana real Wayland, posición exacta y sin XWayland.

### B. Qt6 + LayerShellQt
- Equivalente en KDE, pero añade Qt6 + PyQt/PySide (~200MB) y sigue sin
  soporte en GNOME. Peor coste/beneficio para un OSD de 420×72.

### C. GTK4 sin layer-shell (toplevel normal)
- Funciona en GNOME, pero Wayland no permite posicionar una toplevel:
  el compositor decide. Se perdería el “arriba y centrado”. No resuelve el
  problema, solo cambia de toolkit.

### D. Extensión GNOME Shell / script KWin
- Específico de cada escritorio, dos implementaciones, permisos de extensión
  y APIs inestables. Duplica el OSD actual en vez de sustituirlo.

### E. Seguir con Tk/XWayland
- Cero trabajo, pero depende de XWayland (ausente en sesiones puras), el
  posicionamiento lo controla X11 y `-type notification` no es layer-shell.

## 4. Restricciones y hallazgos

1. **El OSD no debe robar foco**: si la ventana toma teclado, el `Ctrl+V`
   automático y lo que el usuario escriba irían al OSD. Layer-shell con
   `KEYBOARD_MODE_NONE` lo garantiza; en GTK hay que evitar `grab_focus()`.
2. **El venv no ve PyGObject**: `.venv/bin/python -c "import gi"` falla
   (`No module named 'gi'`). El backend GTK debe lanzarse con el **python del
   sistema** (`/usr/bin/python3`), no con `sys.executable`.
3. Para que eso funcione sin depender del paquete instalado, el OSD GTK debe
   ser un **script autocontenido** (stdlib + `gi`), ejecutado por ruta
   (`/usr/bin/python3 …/osd_gtk.py <socket>`), no con `-m local_speech_to_text`.
4. **GNOME no tiene layer-shell**: decisión en runtime, no en instalación.
5. El protocolo `level` (JSON: `recording`, `elapsed`, `rms`, `partial`,
   `hold`) es estable y suficiente; el OSD no necesita IPC nuevo.
6. `gtk4-layer-shell` no está instalado aquí: el sondeo de disponibilidad debe
   ser barato y cacheado (una vez por daemon), no por dictado.

## 5. Recomendación

**Opción A con fallback automático**:

- Backend `gtk-layer` cuando haya sesión Wayland + `zwlr_layer_shell_v1` +
  typelib `Gtk4LayerShell` importable por el python del sistema.
- Backend `tk` (actual) en GNOME, X11 o si falta cualquier pieza.
- Selección **automática y observable** (`doctor` dice cuál y por qué), con
  override `osd_backend = "gtk" | "tk" | "auto"`.
- Sin dependencias obligatorias nuevas: `gtk4`/`python-gobject`/
  `gtk4-layer-shell` van como optdepends.

## 6. Riesgos

| Riesgo | Mitigación |
|---|---|
| GNOME sin layer-shell | fallback Tk automático y documentado |
| Transparencia/rounded no soportada | fondo opaco si el compositor no compone alpha |
| `gi` roto en el python del sistema | sondeo falla → Tk, nunca excepción |
| OSD roba foco | `keyboard_mode none` + test manual (`wtype` mientras graba) |
| Multi-monitor | layer-shell elige salida; config futura `osd_monitor` |
| Script autocontenido se desincroniza del protocolo | test de contrato sobre `format_status`/claves JSON |
