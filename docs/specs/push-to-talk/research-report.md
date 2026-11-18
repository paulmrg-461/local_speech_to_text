# Research — Push-to-talk (mantener tecla para dictar)

Fecha: 2026-11-18 · Estado: cerrado (fase 1) · Autor: DevPaul

## 1. Pregunta

¿Cómo implementar «mantener Win+F → graba; soltar → transcribe» en Linux
(Wayland KDE/GNOME y X11) sin romper el modo toggle, sin privilegios de root
y sin convertirse en un keylogger?

## 2. Estado actual (evidencia en el repo)

| Pieza | Hecho | Evidencia |
|---|---|---|
| Atajo global | Se registra un **comando** que se ejecuta al pulsar | `scripts/setup-hotkey.sh` (KDE `CommandURL`, GNOME `custom-keybinding command`) |
| IPC | El socket acepta `start`, `stop`, `toggle`, `status`… | `daemon.py:401-430` |
| `start` | Idempotente (solo arranca si no graba) | `daemon.py:404-407` |
| `stop` | **No idempotente**: llama a `toggle()` | `daemon.py:408-409` |
| Grabación | Hilo watchdog con `max_record_seconds` y `silence_stop` | `daemon.py:139-174` |
| Patrón de hilo continuo | `WakeWordMonitor` (Event de stop, cola, mute) | `wakeword.py:35-90` |
| Diagnóstico | `doctor` comprueba atajo, servicio, mic, GPU | `cli.py` `cmd_doctor` |

Consecuencia: hoy solo hay **evento de pulsación**. Ni `khotkeysrc`, ni
`gsettings`, ni `xdg-desktop-portal GlobalShortcuts` exponen «tecla soltada»;
son APIs de *activación*, no de estado del teclado. Sin un segundo canal no
existe release.

## 3. Opciones evaluadas

### A. `python-evdev` leyendo `/dev/input/event*` (usuario)
- Lee eventos **globales** sin `EVIOCGRAB`: no secuestra el teclado.
- Requiere pertenecer al grupo `input` (`crw-rw---- root:input` confirmado en
  esta máquina; paquete `python-evdev` en `extra`).
- Latencia de milisegundos, sin root, sin dependencias de escritorio.
- Coste de seguridad: el grupo `input` permite leer **todas** las teclas
  (equivalente funcional a un keylogger). Mitigable con allowlist de
  dispositivos y sin registrar códigos ajenos, pero no elimina el permiso.

### B. `keyd` (demonio root)
- Remapea teclas y puede ejecutar comandos; requiere root y su propio modelo
  de configuración. Un «hold» que lance `local-stt start/stop` obliga a
  sincronizar dos demonios y a duplicar el atajo. Sobredimensionado.

### C. `interception-tools` + `udevmon` (root)
- Permite plugins que ven press/release, pero instala un framework C++ y
  reglas udev root. Misma objeción que B, más superficie.

### D. Script/plugin del compositor (KWin, GNOME Shell)
- KWin no expone key events globales a scripts; KGlobalAccel sigue siendo
  press-only. GNOME Shell no permite extensiones sin publicar y su API de
  atajos también es de activación. En Wayland el aislamiento es deliberado.

### E. Portal `GlobalShortcuts`
- Estandariza el registro, no el ciclo press/release (activación puntual).

### Matriz

| Criterio | A evdev | B keyd | C interception | D compositor | E portal |
|---|---|---|---|---|---|
| Detecta release | ✅ | ✅ | ✅ | ❌ | ❌ |
| Sin root | ✅ | ❌ | ❌ | ✅ | ✅ |
| Sin depender del DE | ✅ | ✅ | ✅ | ❌ | ⚠️ |
| Instalación | grupo `input` | demonio root | udev + root | por DE | por DE |
| Superficie de fallo | baja | media | alta | media | baja |
| Seguridad | ⚠️ keylogger | ⚠️ root | ⚠️ root | ✅ | ✅ |

## 4. Hallazgos que condicionan el diseño

1. **El atajo del compositor debe dejar de gestionar Win+F** cuando el modo
   hold está activo; si no, press se procesaría dos veces (compositor +
   listener). Se conserva Win+Shift+F (historial).
2. **Sin permiso de lectura hay que fallar cerrado**: `push_to_talk=true` sin
   acceso a `/dev/input` no debe dejar el dictado a medias; el daemon sigue
   en modo toggle y `doctor` explica el remedio.
3. **`stop` debe ser idempotente** antes de integrar release; hoy soltar en
   idle arrancaría una grabación (`daemon.py:408`).
4. **Auto-repeat**: `KEY_F` se repite mientras se mantiene; el listener debe
   ignorar repeticiones (`value == 2`) y exigir flanco de subida.
5. **Hotplug**: los `event*` cambian al reconectar teclados; hay que
   redescubrir periódicamente (polling cada 5 s) sin bloquear.
6. **Propiedad de la grabación**: si el dictado lo inició wake word o toggle,
   soltar Win+F no debe cortarlo.
7. **Tap corto**: un toque (<200 ms) debe comportarse como toggle para no
   perder el hábito actual.
8. **Socket `0o777`**: cualquier usuario local puede hoy arrancar el micro o
   parar el daemon (`daemon.py:387`). Es un riesgo independiente que este
   trabajo debe cerrar (`0600`).

## 5. Recomendación

**Opción A**, con estas condiciones:

- Listener **dentro del daemon** (un hilo más, como el wake word), no un
  proceso aparte: comparte lock, estado y ciclo de vida.
- `python-evdev` como extra opcional (`[hold]`), imports lazy.
- Allowlist de dispositivos por nombre (`hold_devices`) y filtro de códigos:
  solo `KEY_LEFTMETA`, `KEY_RIGHTMETA`, `KEY_F` y modificadores.
- Fallback explícito y visible a toggle; nunca degradar en silencio.
- Documentar con claridad que el grupo `input` permite leer el teclado
  completo, y ofrecer la alternativa de un solo dispositivo.

## 6. Riesgos residuales

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Listener muere durante un hold | Grabación sin parar | watchdog `max_record_seconds` + log + `doctor` |
| Teclado Bluetooth reconectado | Atajo muerto hasta redescubrir | polling de dispositivos cada 5 s |
| Usuario añadido a `input` sin re-login | Permiso no efectivo | `doctor` detecta grupo efectivo y avisa |
| Doble disparo con compositor | start/stop espurios | setup desregistra Win+F en modo hold |
| Repetición de tecla | stop prematuro | ignorar `value==2` |
