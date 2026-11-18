# Requisitos — Push-to-talk (EARS)

Formato EARS. Cada requisito es verificable con un test unitario o de
integración; el criterio de aceptación indica el test esperado.

## Funcionales

**RF-1 (evento)**
Cuando `push_to_talk = true` y el usuario pulsa `hold_key` (por defecto
`super+f`), el sistema shall iniciar la grabación en ≤100 ms.
*Criterio:* `HoldStateMachine` emite `start` con un evento `KEY_F` `value=1`
y `KEY_LEFTMETA` mantenido.

**RF-2 (release)**
Cuando hay una grabación propiedad del hold y el usuario suelta la tecla, el
sistema shall parar y transcribir en ≤200 ms.
*Criterio:* segundo evento `KEY_F` `value=0` emite `stop` una sola vez.

**RF-3 (tap)**
Si la tecla se mantiene menos de `hold_min_ms` (200 ms), entonces el sistema
shall tratar la pulsación como el primer `toggle`: la grabación sigue activa
y el siguiente tap la detiene.
*Criterio:* `press`+`release` con Δt=120 ms emite `start` (una vez) y ningún
`stop`; un segundo tap emite `stop`.

> Ajuste respecto a la v1: el `start` es inmediato en el press (RF-1), así
> que un tap no puede emitir un único `toggle` sin parar la grabación recién
> iniciada. El comportamiento observable es el mismo (toque = dictar).

**RF-4 (auto-repeat)**
Mientras la tecla siga pulsada, el sistema shall ignorar eventos con
`value=2`.
*Criterio:* N repeticiones no generan comandos extra.

**RF-5 (propiedad)**
Si la grabación la inició wake word o el modo toggle, cuando el usuario suelta
`hold_key` el sistema shall no detenerla.
*Criterio:* máquina en estado `recording_external` ignora `release`.

**RF-6 (idempotencia)**
Cuando el daemon recibe `stop` estando idle, shall permanecer idle; cuando
recibe `start` grabando, shall no reiniciar la grabación.
*Criterio:* socket `start`/`stop` repetidos no cambian el estado.

**RF-7 (fallback)**
Si `push_to_talk = true` y no hay permisos o `python-evdev`, entonces el
sistema shall mantener el modo toggle operativo y registrar el motivo.
*Criterio:* `HoldListener.start()` devuelve `False`, el daemon arranca igual,
`status` responde y `doctor` reporta.

**RF-8 (hotplug)**
Cuando aparece un teclado nuevo con capacidad `EV_KEY`/`KEY_F`, el sistema
shall empezar a escucharlo en ≤5 s sin reiniciar el daemon.
*Criterio:* fuente falsa que añade un device y emite eventos.

**RF-9 (allowlist)**
Donde `hold_devices` no esté vacío, el sistema shall escuchar solo los
dispositivos cuyo nombre coincida (substring, case-insensitive).
*Criterio:* device «AT Translated Set 2 keyboard» se acepta con
`hold_devices=["AT Translated"]` y se rechaza con `["Logitech"]`.

## Seguridad

**RS-1 (mínimo privilegio)**
El listener shall abrir los dispositivos en solo lectura y shall no llamar a
`EVIOCGRAB`.
*Criterio:* la fuente real se instancia con `grab=False` y `O_RDONLY`.

**RS-2 (no keylogging)**
El listener shall descartar cualquier código de tecla distinto de
`KEY_LEFTMETA`, `KEY_RIGHTMETA`, `KEY_LEFTCTRL`, `KEY_LEFTALT`,
`KEY_LEFTSHIFT` y `KEY_F` antes de cualquier log o callback.
*Criterio:* evento `KEY_A` no produce salida ni cambio de estado.

**RS-3 (socket local)**
El socket IPC shall crearse con permisos `0600`; un proceso de otro usuario
no shall poder enviar comandos.
*Criterio:* `stat(socket_path).st_mode & 0o777 == 0o600`.

**RS-4 (diagnóstico honesto)**
Cuando falte el grupo `input`, el mensaje shall explicar el riesgo (lectura
global del teclado) y la alternativa de allowlist, no solo el comando.
*Criterio:* salida de `doctor` contiene «input» y «keylogger» o equivalente.

## No funcionales

**RNF-1** CPU en reposo: el hilo bloquea en `read()`; sin polling salvo el
redescubrimiento cada 5 s.

**RNF-2** Sin nuevas dependencias obligatorias: `python-evdev` va en el extra
`[hold]`; el paquete AUR lo declara como optdepend.

**RNF-3** Compatibilidad: mismo comportamiento en Wayland (KDE/GNOME) y X11;
sin tocar los atajos existentes salvo desregistrar Win+F cuando hold está
activo.

**RNF-4** Observable: transiciones press/release/tap se registran en
`~/.local/state/local-stt/daemon.log` con una línea por transición (sin
códigos ajenos).
