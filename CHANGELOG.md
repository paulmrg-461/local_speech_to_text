# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
El proyecto sigue [SemVer](https://semver.org/lang/es/) de forma pragmática:
0.x = API de CLI/config todavía puede cambiar.

## [Unreleased]

### Añadido
- `local-stt wakeword`: modelo activo, ruta resuelta (nombre o `.onnx`
  custom), modelos incluidos y `--check` para scripts.
- **Wake word con frase propia sin entrenar**: motor Vosk
  (`wake_word_engine = "vosk"`, `wake_word_phrase = "dev paul"`,
  `--download-vosk`, `wake_word_phrase = "oye computadora"` en español). CPU,
  gramática limitada a la frase; opt-in con extra `[vosk]`. Acepta alias
  (`"dev paul|devpaul"`) y avisa de frases de una sola palabra.
- **Post-proceso opcional con LLM local** (Ollama + Gemma 4):
  `post_process = format|translate`, estilos clean/email/chat/code, timeout con
  fallback al texto crudo, `local-stt llm` y comprobación en `doctor`. Sin
  dependencias Python nuevas y solo `localhost`.

### Corregido
- `doctor` valida el motor de wake word real (Vosk u openWakeWord), el modelo,
  la frase y los alias; la chuleta y `status` muestran motor/frase.
- Descarga de Vosk: sha256 fijado por modelo y extracción que rechaza rutas
  fuera del destino (zip-slip).
- `setup` avisa si el motor Vosk está activo sin dependencias/modelo y de
  frases demasiado cortas.

## [0.3.0] - 2026-11-19

### Añadido
- **OSD nativo Wayland**: backend GTK4 + `gtk4-layer-shell` (capa overlay, sin
  robar foco) lanzado con el python del sistema; fallback automático a Tk en
  GNOME/X11. `osd_backend = auto|gtk|tk`, `osd_margin_top`, `osd_monitor`
  (nombre/índice en GTK), sondeo cacheado y `doctor` informa del backend
  elegido. El título del OSD y la notificación cambian según el modo.
- `local-stt osd`: backend elegido, dependencias y `--check`; `--preview`
  muestra el OSD N segundos con datos sintéticos (verificación visual sin
  dictar).
- `local-stt history --reprocess`: reaplica puntuación/correcciones/números de
  la config actual al historial, con backup `.bak`.
- Wake word: se silencia el aviso de `CUDAExecutionProvider` (el modelo corre
  en CPU por diseño).

### Corregido
- OSD GTK: en Arch `gtk4-layer-shell` se enlaza después de `libwayland` y la
  capa no inicializaba. El daemon/preview añaden `LD_PRELOAD` automáticamente y
  el sondeo exige `Gtk4LayerShell.is_supported()`, así que no se elige GTK
  cuando la capa no puede funcionar.
- CLI: `--lang` ya no pisa `language` de env/TOML al no pasarse; `--lang auto`
  fuerza autodetección aunque el TOML fije idioma.
- `setup` no desregistra `Win+F` si `hold_devices` no coincide con ningún
  teclado (antes dejaba al usuario sin atajo).
- OSD: el parcial se recorta a 300 chars y `query_level` lee hasta newline; un
  timeout puntual ya no cierra el OSD (tolera ~1 s). El backend Tk respeta
  `osd_margin_top`.
- Push-to-talk: el rescaneo de hotplug se reintenta aunque no queden teclados
  (antes quedaba muerto hasta reiniciar).
- Daemon: pid lock (imposible arrancar dos), `umask 077` durante el bind del
  socket, EOF en el socket ya no arranca una grabación, y `reload` aplica
  idioma/beam/VAD sin descargar el modelo en mitad de un dictado.
- `doctor` cuenta como fallo (no aviso) los problemas de push-to-talk cuando
  está activado; `config` normaliza `hold_key`/`osd_backend` ante TOML con
  tipos inesperados; `query_level` cierra siempre el socket.

## [0.2.0] - 2026-11-19

### Añadido
- **Push-to-talk** (`push_to_talk = true`): mantén `hold_key` para grabar y
  suelta para transcribir. Listener `python-evdev` dentro del daemon (release
  real, imposible vía atajos del compositor), tap corto = primer toggle,
  allowlist por teclado (`hold_devices`), hotplug y reload en caliente.
- `local-stt keyboards`: lista teclados legibles y marca los que coinciden con
  la allowlist.
- `doctor`: comprueba `evdev`, grupo `input`, teclado legible, allowlist y
  estado del listener; en modo hold no exige el atajo del compositor.
- `setup`: solo desregistra `Win+F` si hold puede funcionar; si no, conserva
  toggle y explica el comando exacto.
- CI: jobs `build` (wheel + `python-installer` como el PKGBUILD) y `audio`
  (PortAudio); matrix 3.11/3.13/3.14.
- Paquete AUR (`packaging/aur/`): wheel con hatchling, unit de usuario,
  `setup-hotkey.sh`, cuBLAS 12 desde el wheel de PyPI y `python-evdev` como
  optdepend.

### Seguridad
- Socket IPC `0600` (antes `0777`: otro usuario local podía arrancar el micro).
- evdev se abre en solo lectura y sin `EVIOCGRAB`; solo se miran los códigos
  del chord, nunca se registran teclas ajenas.
- Aviso explícito del riesgo del grupo `input` (keylogger-equivalente).

### Corregido
- `stop` por socket en idle ya no arrancaba una grabación (idempotencia).
- Historial: se guardaba dos veces cada dictado.
- `local-stt config` comentaba las listas (`hold_devices`) al guardar.
- Chord con tecla inexistente ya no falla en silencio (`bad-chord`).
- Suite de tests verde en CI slim (skips de audio/GPU/openwakeword) y carrera
  al recrear el socket.

## [0.1.0] - 2026-11-18

- Versión inicial: dictado local con faster-whisper/CUDA, atajo global Win+F,
  portapapeles + auto-paste, OSD, historial, vocabulario/correcciones, wake
  word, TUI de configuración, `doctor`, `setup`, `update`/`uninstall` y
  paquete AUR.
