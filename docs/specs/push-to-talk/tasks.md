# Tareas — Push-to-talk

> **Estado (2026-11-18):** T1-T10 implementadas y con tests. Queda la prueba
> manual con teclado real tras `usermod -aG input` (no ejecutable en CI).

Atómicas y ordenadas. Ninguna se implementa sin aprobar esta lista (fase 4).
Cada una incluye sus tests (éxito / fallo / seguridad cuando aplique).

## T1 · Config y parser de chord
- `hold_key`, `hold_min_ms`, `hold_devices`, `push_to_talk` en `Config` +
  `_ENV_MAP` + defaults.
- `parse_chord("super+f") -> HoldChord(mods={KEY_LEFTMETA, KEY_RIGHTMETA}, key=KEY_F)`.
- Chord inválido ⇒ `None` (no excepción) y warning.
- Tests: válido, alias (`win`, `ctrl+alt+d`), vacío, tecla desconocida,
  modificador desconocido, `hold_min_ms` negativo ⇒ default.

**DoD:** `pytest tests/test_config.py tests/test_hotkey_hold.py -q` verde.

## T2 · `HoldStateMachine` puro
- Eventos `press`/`release`, reloj inyectable, estados del diseño §3.
- Callbacks `on_start`/`on_stop`/`on_toggle` inyectados.
- Tests: hold normal, tap, tap-stops-segundo-toque, auto-repeat, grabación
  externa, release tras watchdog, doble release, dos teclados simultáneos.

**DoD:** cubre RF-1…5; sin imports de `evdev`.

## T3 · Daemon: comandos idempotentes
- `start`/`stop` idempotentes en socket (corrige `daemon.py:408`).
- Origen de grabación (`toggle|wake|hold|socket`).
- Tests: `stop` en idle no graba; `start` grabando no reinicia; `toggle`
  conserva comportamiento; `status` incluye `hold`.

**DoD:** RF-6 y regresión del toggle actual.

## T4 · Fuente de eventos y allowlist
- Protocolo `EventSource`; `FakeSource` en tests.
- `is_keyboard(device)` (EV_KEY + KEY_F); filtro `hold_devices` substring.
- Filtro de códigos permitidos antes de callback/log.
- Tests: acepta/rechaza por nombre, ignora `KEY_A`, hotplug añade/quita.

**DoD:** RF-8, RF-9, RS-2.

## T5 · `EvdevSource` + `HotkeyListener`
- Import lazy; `O_RDONLY`, sin grab; `select` + `read`; reconexión.
- `start()` devuelve `False` con motivo si falta evdev o permiso.
- Redescubrimiento cada 5 s.
- Tests: sin evdev ⇒ `False`; `PermissionError` ⇒ `False` + mensaje;
  fuente falsa ⇒ callbacks en orden.

**DoD:** RF-7, RS-1; CI sin `python-evdev` sigue verde.

## T6 · Integración en el daemon
- Arranque/parada del listener en `start()`/`stop()`.
- `reload` reinicia listener si cambian config/chord/devices.
- Watchdog: si grabación hold excede `max_record_seconds`, no dejar estado
  inconsistente.
- Tests: daemon con fuente falsa inicia/para; reload cambia devices;
  excepción en listener no tumba el daemon.

**DoD:** RF-1, RF-2, RF-9 en integración.

## T7 · `doctor`
- Comprueba: `push_to_talk`, import evdev, grupo `input` efectivo, devices
  legibles, estado del listener (`status.hold`), allowlist vacía (aviso).
- Mensaje accionable con riesgo y alternativa.
- Tests: sin permiso, con permiso simulado, desactivado (no ruido).

**DoD:** RS-4.

## T8 · `setup` y atajos
- `LOCAL_STT_SKIP_TOGGLE=1` ⇒ `setup-hotkey.sh` omite Win+F y conserva
  Win+Shift+F (KDE y GNOME).
- `local-stt setup` lo exporta si `push_to_talk`.
- Tests: el script con la variable no escribe la acción de dictado (grep en
  fichero khotkeysrc temporal / comandos gsettings mockeados).

**DoD:** RNF-3; sin doble disparo.

## T9 · Socket `0600`
- `os.chmod(sock, 0o600)`; test de modo.
- `doctor` avisa si un socket antiguo tenía `0777` (se recrea al arrancar).

**DoD:** RS-3.

## T10 · Docs y empaquetado
- README: sección hold (requisito de grupo, riesgo, allowlist, volver a
  toggle), matriz de interacciones, troubleshooting.
- `pyproject`: extra `hold = ["evdev>=1.7"]`.
- AUR: `python-evdev` en `optdepends`.
- Chuleta de `local-stt setup`.

**DoD:** RNF-2; `ruff` y suite verdes.

## Orden y dependencias

```
T1 → T2 → T3 ─┬→ T6 → T7 → T8 → T10
              ├→ T4 → T5 ┘
              └→ T9
```

## Fuera de alcance (explícito)

- Release sin evdev vía compositor: no existe API.
- Wake word en español: trabajo separado.
- OSD nativo Wayland: trabajo separado.
