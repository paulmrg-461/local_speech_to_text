# Requisitos — OSD nativo Wayland (EARS)

Cada requisito tiene criterio de test. “OSD GTK” = `osd_gtk.py`; “OSD Tk” =
`osd.py` actual.

## Funcionales

**RF-1 (backend automático)**
Cuando `osd_backend = "auto"`, sesión Wayland, `WAYLAND_DISPLAY` definido y el
sondeo GTK/layer-shell es positivo, el sistema shall usar OSD GTK.
*Criterio:* `choose_backend(...) == "gtk"` con esas entradas.

**RF-2 (fallback)**
Si falta layer-shell, GTK, `gi` o la sesión no es Wayland, entonces el sistema
shall usar OSD Tk y shall no fallar al grabar.
*Criterio:* tabla de verdad de `choose_backend`; `_launch_osd` arranca Tk y el
daemon sigue grabando.

**RF-3 (override)**
Donde `osd_backend = "gtk"|"tk"`, el sistema shall respetar el valor aunque el
sondeo diga otra cosa (y avisar en `doctor` si es inviable).
*Criterio:* `choose_backend(forced="tk", probe_ok=True) == "tk"`.

**RF-4 (capa y posición)**
El OSD GTK shall usar `zwlr_layer_shell_v1` en capa `overlay`, anclado arriba,
con margen `osd_margin_top` (default 80) y sin reservar espacio
(`exclusive_zone = -1`).
*Criterio:* revisión de código + captura manual en KWin.

**RF-5 (sin foco)**
El OSD GTK shall configurarse con `KEYBOARD_MODE_NONE` y shall no pedir foco;
lo que el usuario teclee durante la grabación shall ir a la ventana activa.
*Criterio:* manual: con `wtype "hola"` mientras graba, “hola” aparece en el
editor, no en el OSD.

**RF-6 (contenido)**
Mientras graba, el OSD shall mostrar barra de nivel (RMS normalizado a 0.15),
segundos transcurridos y los últimos 90 caracteres del parcial, refrescados a
10 Hz.
*Criterio:* `bar_fraction(0.075) == 0.5`; `format_status({...})` incluye `[s]`
y el parcial recortado.

**RF-7 (ciclo de vida)**
Cuando el socket responda `recording=false` o desaparezca, el OSD shall
cerrarse en ≤400 ms; el daemon shall matarlo al parar la grabación.
*Criterio:* test de `should_exit(info)`; `_kill_osd` usa terminate y espera.

**RF-8 (resiliencia de arranque)**
Si el proceso GTK muere en el primer segundo (typelib roto, sin display), el
daemon shall relanzar el OSD Tk una vez y continuar.
*Criterio:* `_launch_osd` con Popen falso que devuelve `poll()!=None` → segundo
Popen con argv de Tk.

**RF-9 (independencia del venv)**
El OSD GTK shall ejecutarse con el python del sistema por ruta de archivo y
shall importar solo stdlib a nivel de módulo.
*Criterio:* importar `osd_gtk` en CI sin `gi` no lanza; `main()` es quien
importa `gi`; el argv usa `/usr/bin/python3` + ruta.

## Seguridad

**RS-1 (sin privilegios)**
El OSD shall no pedir root, no abrir dispositivos y shall usar el mismo socket
`0600` que ya usa el daemon.

**RS-2 (sin teclado)**
El OSD shall no capturar entrada de teclado ni instalar atajos.

## No funcionales

**RNF-1** CPU: un timer de 100 ms y un socket por tick; sin hilos extra.

**RNF-2** Dependencias: `gtk4`, `python-gobject`, `gtk4-layer-shell` opcionales;
sin pip nuevo, CI sin GTK sigue verde.

**RNF-3** Compatibilidad: KDE Wayland (GTK), GNOME Wayland y X11 (Tk), wlroots
(GTK si layer-shell está).

**RNF-4** Diagnóstico: `doctor` muestra backend elegido, motivo y versión de
`zwlr_layer_shell_v1`; nunca lo cuenta como fallo si Tk funciona.
