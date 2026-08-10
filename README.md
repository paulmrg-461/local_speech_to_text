# Local Speech-to-Text para Linux — RTX 5070 12GB

**Win+F → habla → Win+F → se copia y pega con Ctrl+V.**
100% local, sin nube. Optimizado para tu RTX 5070 con `faster-whisper` en CUDA.

> Funciona en Wayland (GNOME/KDE) y X11. Copia con `wl-copy`/`xclip` y auto-pega con `wtype`/`ydotool`/`xdotool`.

---

## Instalación (EndeavourOS / Arch)

```bash
# 1. Clonar / entrar al proyecto
cd ~/Documents/dev_projects/DevPaul/local_speech_to_text

# 2. Instalar todo (deps sistema + venv + modelo se descarga solo al primer uso)
chmod +x scripts/install.sh scripts/setup-hotkey.sh
./scripts/install.sh

# 3. Configurar atajo Win+F (GNOME Wayland)
./scripts/setup-hotkey.sh

# 4. Iniciar daemon (elige uno)
.venv/bin/local-stt daemon              # foreground, para probar
# o como servicio en background:
systemctl --user enable --now local-stt
```

**Listo.** Presiona `Super+F` (tecla Windows + F), habla, vuelve a presionar `Super+F`. Verás notificación y el texto ya está en el portapapeles. Pega con `Ctrl+V` (o auto-pega si tienes `wtype`/`ydotool`).

---

## Uso

| Comando | Qué hace |
|---|---|
| `local-stt daemon` | Inicia daemon (mantiene modelo en VRAM, ~3GB) |
| `local-stt toggle` | Alterna grabación (lo llama el atajo) |
| `local-stt status` | `recording` / `idle` |
| `local-stt stop` | Detiene daemon |
| `local-stt devices` | Lista micrófonos (elige con `pavucontrol`) |
| `local-stt transcribe audio.wav --copy` | Transcribe un archivo suelto |

### Atajo manual (si el script no te lo configuró)

GNOME: **Configuración → Teclado → Atajos personalizados → +**
- Nombre: `Local STT`
- Comando: `/ruta/completa/.venv/bin/local-stt toggle`
- Atajo: `Super+F`

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

## Configuración (variables de entorno)

| Var | Default | Descripción |
|---|---|---|
| `LOCAL_STT_MODEL` | `large-v3-turbo` | Modelo faster-whisper |
| `LOCAL_STT_LANG` | `es` | `es`, `en`, `auto` (autodetect) |
| `LOCAL_STT_DEVICE` | `cuda` | `cuda` o `cpu` |
| `LOCAL_STT_COMPUTE` | `float16` | `float16`, `int8_float16`, `float32` |
| `LOCAL_STT_AUTO_PASTE` | `1` | `1` intenta `Ctrl+V` automático |
| `LOCAL_STT_MAX_SECS` | `120` | Auto-stop tras 2 min |

---

## Cómo funciona (arquitectura)

```
Win+F (gsettings atajo) → `local-stt toggle` → socket /tmp/local-stt.sock
                                              → Daemon (modelo en VRAM)
                                              → AudioRecorder (sounddevice, 16kHz)
                                              → Transcriber (faster-whisper CUDA)
                                              → wl-copy / xclip + notify + wtype Ctrl+V
```

- El **daemon** carga el modelo una vez y lo mantiene en VRAM (arranque ~10s, luego transcripción <1s).
- Sin daemon cada transcripción recargaría el modelo (lento).
- Audio va por PipeWire/PulseAudio, 16kHz mono.

---

## Troubleshooting

**`nvidia-smi` no funciona / fallback a CPU**
- Instala drivers: `sudo pacman -S nvidia nvidia-utils cuda` y reinicia. Verifica `nvidia-smi`.
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

**Texto vacío / no entiende**
- Habla más cerca del micro, revisa volumen en `pavucontrol`.
- Prueba `LOCAL_STT_LANG=auto` o `LOCAL_STT_LANG=en` si mezclas idiomas.
- Test con archivo: `local-stt transcribe test.wav`.

---

## Desinstalar

```bash
systemctl --user disable --now local-stt 2>/dev/null
gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "[]"
rm -rf .venv
```

## Licencia

MIT
