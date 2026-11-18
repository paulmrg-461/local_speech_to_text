# Local Speech-to-Text para Linux — RTX 5070 12GB

**Win+F → habla → Win+F → se copia y pega con Ctrl+V.**
100% local, sin nube. Optimizado para tu RTX 5070 con `faster-whisper` en CUDA.

> Funciona en Wayland (GNOME/KDE) y X11. Copia con `wl-copy`/`xclip` y auto-pega con `wtype`/`ydotool`/`xdotool`.
> Si el daemon está apagado, el atajo **lo arranca solo** (espera el arranque del modelo y empieza a grabar).

---

## Instalación (EndeavourOS / Arch)

```bash
# 1. Clonar / entrar al proyecto
cd ~/Documents/dev_projects/DevPaul/local_speech_to_text

# 2. Instalar todo (deps sistema + venv + config + modelo pre-descargado)
chmod +x scripts/install.sh scripts/setup-hotkey.sh
./scripts/install.sh

# 3. Configurar atajo Win+F (KDE Plasma 6 por defecto; GNOME con variable)
./scripts/setup-hotkey.sh                          # KDE Plasma 6: Meta+F
# GNOME: LOCAL_STT_DESKTOP=gnome ./scripts/setup-hotkey.sh
# Auto-detectar: LOCAL_STT_DESKTOP=auto ./scripts/setup-hotkey.sh

# 4. Iniciar daemon y verificar todo
systemctl --user enable --now local-stt
.venv/bin/local-stt doctor
```

**Listo.** Presiona `Super+F` (tecla Windows + F), habla, vuelve a presionar `Super+F`. Verás notificación y el texto ya está en el portapapeles. Pega con `Ctrl+V` (o auto-pega si tienes `wtype`/`ydotool`).

---

## Uso

| Comando | Qué hace |
|---|---|
| `local-stt daemon` | Inicia daemon (mantiene modelo en VRAM, ~3GB) |
| `local-stt toggle` | Alterna grabación; **auto-arranca el daemon si no corre** |
| `local-stt status` | `recording` / `idle` |
| `local-stt stop` | Detiene daemon |
| `local-stt devices` | Lista micrófonos (elige con `pavucontrol`) |
| `local-stt history` | Últimas 10 transcripciones |
| `local-stt history --copy 2` | Copia al portapapeles la antepenúltima (`--copy` = última) |
| `local-stt download` | Pre-descarga el modelo (primer uso instantáneo) |
| `local-stt doctor` | Diagnóstico: GPU, CUDA, daemon, atajo, clipboard, micro |
| `local-stt transcribe audio.wav --copy` | Transcribe un archivo suelto |

### Dictado con puntuación hablada

Activo por defecto (`dictation_commands = true`). Ejemplos:

| Dices | Sale |
|---|---|
| "hola coma qué tal punto" | `Hola, qué tal.` |
| "punto y coma" / "dos puntos" | `;` / `:` |
| "punto y aparte" / "nueva línea" | `.` + salto de línea |
| "abrir paréntesis … cerrar paréntesis" | `( … )` |
| "abrir comillas … cerrar comillas" | `" … "` |
| "signo de interrogación" | `?` |
| "guion" / "barra" / "arroba" | `-` / `/` / `@` |

### Vocabulario y correcciones

Whisper reconoce mejor tus nombres/términos si se los enseñas:

```bash
local-stt vocab add 'DevPaul' 'FastAPI' 'ydotool'   # initial_prompt
local-stt correct 'dev pablo' 'DevPaul'             # corrección post-transcripción
local-stt vocab                                      # ver / list
local-stt reload                                     # aplicar sin reiniciar
```

Archivos: `~/.config/local-stt/vocabulary.txt` (un término por línea) y
`corrections.txt` (líneas `mal -> bien`).

### OSD con nivel de voz y texto en vivo

Al grabar aparece un indicador flotante arriba-centro: barra de nivel de tu
voz en tiempo real (verde = te oye) + la transcripción **parcial mientras
hablas**. Se cierra solo al parar. Desactivable:

```toml
overlay = false         # sin OSD
partial_results = false # sin texto en vivo
```

### Recuperar dictados anteriores

- **`Win+Shift+F`** → selector visual (wofi) de los últimos 20 dictados → Enter copia y pega. Requiere `sudo pacman -S wofi`.
- `local-stt history` → listado; `local-stt history --copy 2` → copia la antepenúltima.

### Cambiar config sin reiniciar

Edita `~/.config/local-stt/config.toml` y ejecuta `local-stt reload`
(modelo/idioma/vocab/correcciones al vuelo; el modelo solo se recarga si cambió).

### Manos libres: wake word (opcional)

```bash
.venv/bin/pip install 'local-speech-to-text[wakeword]'   # openwakeword + onnxruntime
```

```toml
wake_word = true          # di "hey jarvis" y el dictado empieza solo
wake_word_model = "hey_jarvis"   # alexa, hey_mycroft... o ruta a .onnx custom
wake_word_threshold = 0.5
```

El micrófono queda escuchando en CPU (~0% GPU). Durante el dictado se pausa
para no re-dispararse. Apagado por defecto: `wake_word = false` + `local-stt reload`.

### Atajo manual (si el script no te lo configuró)

**KDE Plasma 6 (default):** **Ajustes del sistema → Atajos → Atajos personalizados → Añadir → Orden/URL**
- Nombre: `Local STT`
- Orden: `/ruta/completa/.venv/bin/local-stt toggle`
- Activador: `Meta+F` (Win+F)

**GNOME:** **Configuración → Teclado → Atajos personalizados → +**
- Nombre: `Local STT`
- Comando: `/ruta/completa/.venv/bin/local-stt toggle`
- Atajo: `Super+F`
- O automático: `LOCAL_STT_DESKTOP=gnome ./scripts/setup-hotkey.sh`

KDE: **Preferencias → Atajos → Añadir comando** → mismo comando → `Meta+F`

---

## Modelos y VRAM (RTX 5070 12GB)

| Modelo | VRAM (float16) | Velocidad | Precisión ES |
|---|---|---|---|
| `tiny` | ~1 GB | ⚡⚡⚡ | baja |
| `small` | ~2 GB | ⚡⚡ | media |
| `medium` | ~3 GB | ⚡ | buena |
| **`large-v3-turbo`** | **~4 GB** | **⚡ (6× vs large-v3)** | **excelente — recomendado** |
| `large-v3` | ~10 GB | lento | máxima |
| `distil-large-v3` | ~6 GB | ⚡ | muy buena |

Cambiar modelo:

```bash
LOCAL_STT_MODEL=medium local-stt daemon
# o permanente en ~/.config/systemd/user/local-stt.service -> Environment=
```

Si te quedas sin VRAM: `LOCAL_STT_COMPUTE=int8_float16` (mitad de VRAM, poca pérdida).

---

## Configuración

Edita `~/.config/local-stt/config.toml` (lo crea el instalador) y reinicia con
`systemctl --user restart local-stt`. Las variables de entorno siguen
funcionando y **ganan** sobre el TOML:

```toml
model = "large-v3-turbo"   # tiny, base, small, medium, large-v3, distil-large-v3
language = "es"            # "auto" autodetecta
device = "cuda"
compute_type = "float16"   # int8_float16 = mitad de VRAM
beam_size = 5
auto_paste = true
dictation_commands = true  # puntuación hablada
silence_stop = false       # true = manos libres: para tras 1.5s de silencio
```

Equivalencias de entorno: `LOCAL_STT_MODEL`, `LOCAL_STT_LANG`, `LOCAL_STT_DEVICE`,
`LOCAL_STT_COMPUTE`, `LOCAL_STT_BEAM`, `LOCAL_STT_AUTO_PASTE`,
`LOCAL_STT_DICTATION_COMMANDS`, `LOCAL_STT_SILENCE_STOP`, `LOCAL_STT_SILENCE_MS`,
`LOCAL_STT_MAX_SECS`.

---

## Cómo funciona (arquitectura)

```
Win+F (khotkeys/gsettings atajo) → `local-stt toggle` → socket /tmp/local-stt.sock
                        │ (si el daemon no corre: lo arranca vía systemd y espera)
                        ▼
                       Daemon (modelo en VRAM)
                       → AudioRecorder (sounddevice, 16kHz, RMS para silencio)
                       → Transcriber (faster-whisper CUDA, cuBLAS 12 precargada)
                       → text_cleaner ("punto y coma" → ";")
                       → historial JSONL + wl-copy / xclip + notify + wtype Ctrl+V
```

- El **daemon** carga el modelo una vez y lo mantiene en VRAM (arranque ~10s, luego transcripción <1s).
- Sin daemon cada transcripción recargaría el modelo (lento).
- **cuBLAS 12**: Arch instala CUDA 13 pero ctranslate2 necesita `libcublas.so.12`;
  se trae por pip (`nvidia-cublas-cu12`) y se precarga con `ctypes` al iniciar (ver `cuda_libs.py`).
- Audio va por PipeWire/PulseAudio, 16kHz mono.

---

## Troubleshooting

**`nvidia-smi` dice "Driver/library version mismatch"**
- Actualizaste `nvidia-utils` sin reiniciar. **Reinicia el equipo.**
- Mientras tanto la transcripción CUDA puede seguir funcionando (el runtime no usa NVML).

**CUDA falla con "Library libcublas.so.12 is not found"**
- Arch instala CUDA 13 y ctranslate2 (compilado para CUDA 12) no la encuentra.
- Solución ya incluida: `.venv/bin/pip install nvidia-cublas-cu12` (se precarga sola).
- Verifica: `local-stt doctor`.

**`nvidia-smi` no funciona / fallback a CPU**
- Instala drivers: `sudo pacman -S nvidia nvidia-utils` y reinicia. Verifica `nvidia-smi`.
- El daemon hace fallback automático a CPU si no hay CUDA, pero será 5-10× más lento.

**No graba / micrófono equivocado**
- `local-stt devices` y elige default en `pavucontrol` → Entrada.
- `arecord -l` y `pactl list sources` para debug.

**Wayland no pega automático**
- Instala `wtype`: `yay -S wtype` o `paru -S wtype`
- Alternativa: `ydotool` (necesita `sudo systemctl enable --now ydotool`)
- Si nada, simplemente haz `Ctrl+V` manual (el texto ya está copiado).

**Atajo no dispara**
- Verifica: `gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings`
- Debe aparecer `/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom-local-stt/`
- Revisa que el comando apunte a la ruta absoluta de `.venv/bin/local-stt`.
- En KDE: Ajustes del sistema → Atajos → Atajos personalizados → Local STT.

**Texto vacío / no entiende**
- Habla más cerca del micro, revisa volumen en `pavucontrol`.
- Prueba `LOCAL_STT_LANG=auto` o `LOCAL_STT_LANG=en` si mezclas idiomas.
- Test con archivo: `local-stt transcribe test.wav`.

**Diagnóstico completo en un comando**
- `local-stt doctor` (GPU, CUDA, cuBLAS, daemon, modelo, atajo, clipboard, micro).

---

## Desinstalar

```bash
systemctl --user disable --now local-stt 2>/dev/null
gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "[]"
rm -rf .venv
```

## Licencia

MIT
