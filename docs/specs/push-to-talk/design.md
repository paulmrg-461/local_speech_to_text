# Diseño — Push-to-talk

Fase 3. Implementa los requisitos de `requirements.md` con el enfoque
recomendado en `research-report.md` (evdev en el daemon, opcional, fallback
explícito).

## 1. Arquitectura

```
 compositor (KDE/GNOME)                 teclado físico
   │  Win+Shift+F (historial)              │ EV_KEY
   │  (Win+F SOLO si hold está apagado)    ▼
   │                                  /dev/input/event*  (root:input, 0660)
   ▼                                       │
 local-stt toggle ──socket──►  Daemon ◄────┴── HotkeyListener (hilo)
                                 │                 │
                                 │          HoldStateMachine (puro)
                                 ▼                 │
                        AudioRecorder/Transcriber  └─ callbacks start/stop
```

Todo vive en el daemon: comparte lock, estado de grabación y ciclo de vida.
No hay proceso nuevo ni IPC nuevo.

### Módulos

| Módulo | Responsabilidad | Dependencias |
|---|---|---|
| `hotkey_hold.py` | parser de chord, máquina de estados, listener evdev | stdlib + `evdev` lazy |
| `daemon.py` | origen de grabación, comandos idempotentes, arranque/parada del listener | `hotkey_hold` lazy |
| `config.py` | 4 campos nuevos + env | — |
| `cli.py` (`doctor`, `setup`) | diagnóstico y desregistro del atajo | `hotkey_hold` lazy |

`evdev` solo se importa dentro de `EvdevSource`; el resto del módulo es
importable sin la dependencia (tests en CI sin `python-evdev`).

## 2. Configuración

```toml
push_to_talk = false        # true: mantener la tecla para dictar
hold_key = "super+f"        # modificadores+tecla; alias: win/meta, ctrl, alt, shift
hold_min_ms = 200           # por debajo se considera tap (toggle)
hold_devices = []           # nombres (substring); [] = todos los teclados
```

Env: `LOCAL_STT_PUSH_TO_TALK`, `LOCAL_STT_HOLD_KEY`,
`LOCAL_STT_HOLD_MIN_MS`, `LOCAL_STT_HOLD_DEVICES` (lista separada por comas).
Se sigue la precedencia CLI > env > TOML > defaults.

`hold_key` inválido ⇒ warning al cargar config y `push_to_talk` efectivo
`false`; nunca excepción al arrancar.

## 3. Máquina de estados

Normaliza eventos evdev a `press` / `release` (ignora `value=2`) y decide con
un reloj inyectable.

| Estado | Evento | Acción | Nuevo estado |
|---|---|---|---|
| `IDLE` | press | `start(origin=hold)`, `t0=now` | `ARMED` |
| `ARMED` / `TAP_OPEN` | press | `t0=now` (nuevo gesto) | igual |
| `ARMED` | release, Δ≥min | `stop()` | `IDLE` |
| `ARMED` | release, Δ<min | nada (el press ya arrancó: equivale a toggle) | `TAP_OPEN` |
| `TAP_OPEN` | release, Δ<min | `stop()` | `IDLE` |
| `EXTERNAL` | press/release | ignora | `EXTERNAL` |

`EXTERNAL` se activa cuando la grabación la inicia wake word, `toggle` o el
socket; se sale al parar. Si la grabación termina por watchdog mientras el
hold sigue pulsado, el release se ignora (no `stop` sobre idle).

La decisión «tap vs hold» se toma **al soltar**, pero el `start` es inmediato
(RF-1); el tap no genera una transcripción vacía porque no se envía `stop`
en el primer toque.

## 4. Listener

```text
HotkeyListener.start()
  ├─ si falta evdev o permiso → False + motivo (daemon sigue en toggle)
  ├─ descubrir teclados (EV_KEY + KEY_F; filtro hold_devices)
  ├─ hilo: select() sobre devices; read() bloqueante
  │    └─ filtrar códigos → máquina → callbacks
  └─ cada 5 s: redescubrir si cambió el conjunto de /dev/input/event*
```

- Apertura `O_RDONLY`, sin `EVIOCGRAB` (RS-1).
- Filtro previo a logs: solo modificadores + tecla del chord (RS-2).
- ReDescubrimiento: compara `(path, name)` con el set activo; añade/quita sin
  reiniciar el hilo principal.
- Errores de lectura (`ENODEV` al desconectar) ⇒ cierra ese fd y continúa.

## 5. Integración en el daemon

- `_start_recording(origin: str)` / `_stop_and_transcribe()` registran el
  origen (`toggle|wake|hold|socket`).
- Comandos IPC (corrección de bug):
  - `start`: si no graba → inicia (origen `socket`); si graba → `ok` sin cambios.
  - `stop`: si graba → para; si no → `ok` sin cambios.
  - `toggle`: sin cambios.
- `status` añade `hold` (running/disabled/no-permission) para `doctor`.
- El listener se arranca en `Daemon.start()` y se para en `stop()` (mismo
  patrón que `WakeWordMonitor`).
- `reload` reevalúa `push_to_talk`, chord y devices; reinicia solo el listener.

## 6. Atajos y setup

Con `push_to_talk=true` el compositor **no** debe ejecutar `local-stt toggle`
en Win+F: el listener gestiona press y release. `cmd_setup` exporta
`LOCAL_STT_SKIP_TOGGLE=1` y `setup-hotkey.sh` omite la acción de dictado,
manteniendo Win+Shift+F. Al desactivar hold, `local-stt setup` vuelve a
registrarla.

## 7. Seguridad

- Socket `0600` (RS-3); el `unlink` de arranque ya fuerza recreación.
- `doctor`: comprueba grupo efectivo (`os.getgroups()`), import de `evdev`,
  al menos un device legible y estado del listener. Mensaje con el riesgo
  («el grupo input permite leer todo el teclado») y la allowlist como
  mitigación (RS-4).
- Sin telemetría ni persistencia de códigos: solo líneas de transición
  (`press`, `release`, `tap`, `stop`) en `daemon.log`.

## 8. Trade-offs

| Decisión | A favor | En contra |
|---|---|---|
| evdev en el daemon | release real, sin root, sin DE | grupo `input` = lectura global |
| `start` inmediato en press | latencia ≤100 ms | lógica tap algo más compleja |
| Listener in-process | sin IPC/proceso extra | un fallo afecta al daemon (aislado con try) |
| Atajo del compositor desregistrado | sin doble disparo | si el listener falla, hay que reactivar toggle |
| `python-evdev` opcional | CI y usuarios sin hold intactos | dos rutas que probar |

Alternativas descartadas: `keyd`/`interception-tools` (root, framework extra),
script de compositor (no hay release en Wayland), portal GlobalShortcuts
(activación puntual).

## 9. Plan de pruebas

| Nivel | Qué | Requisitos |
|---|---|---|
| Unitario puro | `HoldStateMachine` (hold, tap, tap-stop, repeat, externo, watchdog) | RF-1…6 |
| Unitario puro | `parse_chord` (alias, inválidos, orden de modificadores) | RF-1, config |
| Unitario | allowlist de devices y filtro de códigos (fuente falsa) | RF-8, RF-9, RS-2 |
| Unitario | `HoldListener.start()` sin evdev / sin permiso → `False` y toggle intacto | RF-7 |
| Integración | daemon: `start`/`stop` idempotentes, `status` con `hold` | RF-6, RF-7 |
| Seguridad | `stat(socket).st_mode == 0600` | RS-3 |
| Manual | teclado real tras `usermod -aG input` | RF-1, RF-2, RNF-3 |

CI sigue sin `python-evdev`: la fuente falsa cubre el 100 % de la lógica.

## 10. Despliegue

1. Campos de config y máquina de estados (sin activar nada).
2. Listener + integración, apagado por defecto.
3. `doctor` y `setup`; el modo hold se anuncia como opt-in.
4. README: requisito de grupo, riesgo, allowlist y cómo volver a toggle.
5. AUR: `python-evdev` en `optdepends`.
