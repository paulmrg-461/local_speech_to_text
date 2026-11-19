# Local Speech-to-Text for Linux — NVIDIA RTX 5070 12GB

**Win+F → speak → Win+F → your text is copied & pasted.**
100% local voice dictation. No cloud, no telemetry, no subscription. Built on `faster-whisper` with CUDA, tuned for an RTX 5070 (12GB) on Arch Linux / EndeavourOS.

> Works on Wayland (KDE Plasma 6, GNOME) and X11. Copies via `wl-copy`/`xclip`, auto-pastes via `wtype`/`ydotool`/`xdotool`.
> If the daemon is not running when you press the hotkey, **it starts it for you** (waits for the model to load, then starts recording on that same keypress).

## Features

| Feature | Description |
|---|---|
| 🔥 GPU transcription | `large-v3-turbo` on CUDA (float16): a short clip transcribes in well under a second |
| ⌨️ Global hotkey | `Win+F` toggles dictation from any app. `Win+Shift+F` opens a visual picker of past dictations |
| 📋 Clipboard + auto-paste | Result is copied and `Ctrl+V` is injected automatically (or paste manually) |
| 🗣️ Spoken punctuation | Say *"punto y coma"*, *"nueva línea"*, *"abrir paréntesis"*… get `;`, a line break, `(` |
| 📖 Custom vocabulary & corrections | Teach Whisper your names/jargon (`initial_prompt`) and fix recurring mistakes post-hoc |
| 🖥️ Live OSD | Floating indicator with a real-time voice-level bar **and partial transcription while you speak**. Native Wayland layer-shell on KDE/wlroots; Tk/XWayland fallback elsewhere |
| 🕘 History | Last 100 dictations saved locally (`local-stt history`, wofi/rofi picker, re-copy any entry) |
| 🔥 Hot reload | Change model/language/vocabulary without restarting the daemon (`local-stt reload`) |
| 🤚 Wake word (optional) | Say **"hey jarvis"** and dictation starts — no keyboard at all (CPU, openWakeWord) |
| ✋ Push-to-talk (optional) | **Hold Win+F** to record, release to transcribe (real key release via `evdev`; see [Push-to-talk](#push-to-talk-hold-to-dictate)) |
| 🩺 `local-stt doctor` | One command diagnoses GPU, CUDA, daemon, hotkey, clipboard tools and microphone |

---

## Quick start (everything in one command)

**Option A — Arch/EndeavourOS (AUR package, recommended):**

```bash
yay -S local-stt              # from AUR: no venv in your home, deps via pacman
local-stt setup              # system deps, hotkeys, service start, doctor, cheat sheet
```

**Option B — any distro (clone + venv):**

```bash
cd ~/Documents/dev_projects/DevPaul/local_speech_to_text
chmod +x scripts/*.sh
./scripts/install.sh          # 1. venv + Python deps + config + systemd unit + model download
.venv/bin/local-stt setup     # 2. system deps, hotkeys, service start, doctor, cheat sheet
```

`local-stt setup` is idempotent — run it as many times as you want; it only
fixes what's missing and ends with `local-stt doctor` plus a cheat sheet of
every interaction.

If anything is still red after setup, check
[Post-install actions](#post-install-actions) below — the usual two are a
**reboot** (if you recently updated the NVIDIA driver) and a **session
re-login on KDE** (Plasma doesn't hot-reload custom shortcuts).

## Detailed installation

### AUR (`local-stt`)

The PKGBUILD lives in [`packaging/aur/`](packaging/aur/). It builds the wheel
with `hatchling`, installs it with `python-installer` (no venv, no PEP 668
hacks) and — because Arch ships CUDA 13 while `ctranslate2` is compiled
against CUDA 12 — bundles the cuBLAS 12 libs from the PyPI wheel into
`/usr/lib/local-stt/cublas/`, where the daemon preloads them at runtime
(`cuda_libs.py`).

- Python deps come from pacman/AUR (`python-faster-whisper`, `python-sounddevice`, …).
- The systemd unit uses `ExecStart=/usr/bin/local-stt daemon`.
- Not in the AUR yet? Build it locally: `cd packaging/aur && makepkg -si`.
- To remove the *system* files use `sudo pacman -R local-stt`; `local-stt
  uninstall` only cleans the user-level pieces (service, hotkeys, and with
  `--purge` your config/history — it detects a packaged install and won't
  touch `/usr`).

### Clone + `install.sh`

`install.sh` does all of the following:
1. Installs system dependencies (Arch; safe to re-run).
2. Creates `.venv` and installs the package with `pip install -e .` (this includes `nvidia-cublas-cu12` for the CUDA 12/13 fix below).
3. Writes an editable config to `~/.config/local-stt/config.toml` (only if it doesn't already exist).
4. Installs the systemd user service `local-stt.service`.
5. **Pre-downloads the model** (~1.5GB, one time) so your first real dictation is instant.

`local-stt setup` then:
1. Checks the optional system tools (`wl-clipboard`, `wtype`, `wofi`…) and prints one `pacman` command with everything you're missing.
2. Ensures the model is downloaded.
3. Registers both hotkeys (`Win+F` dictation, `Win+Shift+F` history picker) — auto-detects KDE/GNOME.
4. Enables and starts the daemon service.
5. Runs `local-stt doctor` and prints the interaction cheat sheet.

Manual equivalent, if you prefer each step by hand:

```bash
./scripts/setup-hotkey.sh                 # KDE Plasma 6 by default
# GNOME:  LOCAL_STT_DESKTOP=gnome ./scripts/setup-hotkey.sh
# Auto:   LOCAL_STT_DESKTOP=auto ./scripts/setup-hotkey.sh
systemctl --user enable --now local-stt
.venv/bin/local-stt doctor
```

**You're done.** Press `Super+F` (the Windows key + F), speak, press `Super+F`
again. A notification confirms the text is in your clipboard; it is also
auto-pasted with `Ctrl+V` where your cursor was.

## Post-install actions (only if `doctor` shows something red)

| Symptom | Action | Why |
|---|---|---|
| `nvidia-smi` fails with *Driver/library version mismatch* | **Reboot** | You updated `nvidia-utils` without restarting; the running kernel still has the old module. CUDA may keep working meanwhile, but fix it properly. |
| New hotkeys (`Win+Shift+F`) don't fire on KDE | **Log out / log in** | Plasma 6 doesn't hot-reload `khotkeysrc`. After re-login they appear in *System Settings → Shortcuts → Custom Shortcuts*. |
| `doctor` warns about `kdotool` | Optional: `yay -S kdotool` | Exact focused-window detection for per-app vocabulary. Without it the KWin fallback is used (slower, best-effort). |
| You want hands-free | `pip install 'local-speech-to-text[wakeword]'` + `local-stt config` → `wake_word = true` | Adds the "hey jarvis" monitor (CPU). |

## Interaction cheat sheet

| Interaction | What happens |
|---|---|
| **`Win+F` → speak → `Win+F`** | Dictated text lands in your clipboard **and** is pasted with `Ctrl+V` |
| **`Win+Shift+F`** | Visual picker (wofi) of your last 20 dictations → Enter pastes the chosen one |
| **Say "hey jarvis"** (if wake word is on) | Dictation starts with no keyboard at all |
| **Hold `Win+F`** (if push-to-talk is on) | Records while held; releasing transcribes. A quick tap behaves like the normal toggle |
| **`local-stt translate`** | Toggle: dictate in your language, the output is pasted in English |
| **`local-stt config`** | Interactive menu for every setting (Enter keeps each value) |
| **`local-stt keyboards`** | Lists readable keyboards and marks which ones your `hold_devices` allowlist matches |
| **`local-stt reload`** | Applies config changes instantly (no restart, no VRAM loss) |
| **`local-stt doctor`** | Diagnoses GPU, CUDA, daemon, hotkeys, clipboard tools, mic |

Spoken punctuation while dictating: *"coma"* → `,` · *"punto"* → `.` ·
*"punto y coma"* → `;` · *"punto y aparte" / "nueva línea"* → line break ·
*"abrir/cerrar paréntesis"* · *"abrir/cerrar comillas"* · *"signo de
interrogación"* · *"guion"* · *"barra"* · *"arroba"*.

## Push-to-talk (hold to dictate)

Optional mode: **hold `Win+F`** while you speak, **release to transcribe**.

```bash
.venv/bin/pip install 'local-speech-to-text[hold]'   # añade python-evdev
sudo usermod -aG input "$USER"                       # luego cierra sesión y entra
.venv/bin/local-stt config                           # push_to_talk = on
```

```toml
push_to_talk = true
hold_key = "super+f"   # modificadores + tecla
hold_min_ms = 200      # por debajo se trata como tap (primer toggle)
hold_devices = []      # [] = todos los teclados; mejor limita por nombre
```

How it works and what to expect:

- The daemon reads key **press and release** from `/dev/input` (`python-evdev`,
  read-only, never grabs the device). No compositor API exposes key release.
- With the mode on, `local-stt setup` stops registering `Win+F` in KDE/GNOME
  (the listener owns it) and keeps `Win+Shift+F` for history. Turning it off
  and re-running setup restores the normal toggle shortcut.
- A **short tap** (< `hold_min_ms`) acts as the first toggle: recording keeps
  going and the next tap stops it.
- If `evdev` is missing or the user cannot read `/dev/input`, the daemon keeps
  working in toggle mode and `local-stt doctor` says exactly what is missing.
- `local-stt keyboards` lists the readable keyboards and marks which ones the
  `hold_devices` allowlist matches, so you can copy the exact substring.

> [!WARNING]
> Membership in the `input` group lets a process read **every** keystroke,
> which is equivalent to a keylogger. `local-stt` only looks at the chord's
> key and modifiers, but the permission is the real boundary: restrict it with
> `hold_devices = ["AT Translated"]` (substring of `evdev`'s device name) if you
> prefer to trust only your physical keyboard.

## Requirements

**Hardware / OS**
- NVIDIA GPU with ≥4GB VRAM (developed and tuned on an RTX 5070 12GB; any CUDA card works)
- Linux with PipeWire or PulseAudio (Arch / EndeavourOS instructions below)
- A working microphone (check with `pavucontrol`)

**System packages (Arch)**

```bash
sudo pacman -S --needed python python-pip portaudio wl-clipboard libnotify wofi
# Optional but recommended for auto-paste on Wayland:
sudo pacman -S --needed wtype        # sends Ctrl+V on KDE/GNOME Wayland
# Alternative: ydotool (needs `sudo systemctl enable --now ydotool`)
```

> Other distros: install the equivalents (`portaudio19-dev`, `wl-clipboard`, `libnotify-bin`, `rofi` or `wofi`).

**NVIDIA driver**
- Any recent proprietary driver (580+ recommended). **If you just updated `nvidia-utils`, reboot before filing any bug** — a kernel/userspace mismatch makes `nvidia-smi` fail with `Driver/library version mismatch` even though CUDA may still work.
- ⚠️ **CUDA note (Arch)**: the `cuda` package ships CUDA 13 (`libcublas.so.13`), but the `ctranslate2` wheel used by `faster-whisper` is built against CUDA 12 and does `dlopen("libcublas.so.12")` at runtime. This project solves it transparently: the pip package `nvidia-cublas-cu12` is installed into the venv and **preloaded with `ctypes`** before the model loads (see `src/local_speech_to_text/cuda_libs.py`). No wrappers, no `LD_LIBRARY_PATH`, no system changes.

---

## Usage

> The full install flow is described in
> [Quick start](#quick-start-everything-in-one-command). Commands below are
> for day-to-day use.

| Command | What it does |
|---|---|
| `local-stt daemon` | Runs the daemon in the foreground (keeps the model in VRAM, ~3GB) |
| `local-stt toggle` | Toggles recording. **Auto-starts the daemon if it's down** and starts recording on the same keypress |
| `local-stt status` | `recording` / `idle` |
| `local-stt stop` | Stops the daemon |
| `local-stt devices` | Lists microphones (pick the default in `pavucontrol` → Input) |
| `local-stt history` | Shows the last 10 transcriptions |
| `local-stt history --copy 2` | Copies the second-to-last one (`--copy` alone = the latest) |
| `local-stt pick` | Visual picker (wofi/rofi) of the last 20 dictations; Enter copies & pastes the chosen one |
| `local-stt download` | Pre-downloads the model (first use becomes instant) |
| `local-stt reload` | Re-reads config (TOML + env) without restarting the daemon |
| `local-stt vocab [list\|add\|remove]` | Manage the custom vocabulary passed as Whisper's `initial_prompt` |
| `local-stt correct 'bad' 'good'` | Add a post-transcription correction rule |
| `local-stt config` | Interactive config editor (shows config when run without a TTY) |
| `local-stt translate` | Toggle translation mode: dictate in your language, output in English |
| `local-stt doctor` | Full diagnosis: GPU, CUDA, cuBLAS, daemon, model, hotkey, clipboard tools, mic |
| `local-stt setup` | One-command onboarding: system deps, model, hotkeys, service, doctor + cheat sheet |
| `local-stt update` | Self-update: git pull → pip install → tests → daemon restart |
| `local-stt uninstall [--yes] [--purge]` | Remove service + hotkeys (add `--purge` for config/history/.venv) |
| `local-stt stats` | Usage stats: dictations, words, minutes dictated, 14-day histogram |
| `local-stt bench [file]` | Compare models on your GPU with your own audio (records from mic if no file) |
| `local-stt transcribe audio.wav --copy` | One-off transcription of an audio file |

Logs (useful for debugging): `journalctl --user -u local-stt -f`

### Hotkeys

| Keys | Action |
|---|---|
| `Win+F` | Start/stop dictation |
| `Win+Shift+F` | Pick & paste a previous dictation (requires `wofi`) |

Manual setup if the script couldn't do it:
- **KDE Plasma 6:** *System Settings → Shortcuts → Custom Shortcuts → Add → Command/URL* — command `<repo>/.venv/bin/local-stt toggle`, trigger `Meta+F`.
- **GNOME:** *Settings → Keyboard → Custom Shortcuts → +* — same command, binding `<Super>f`.

### Spoken punctuation (Spanish, on by default)

| You say | You get |
|---|---|
| "hola coma qué tal punto" | `Hola, qué tal.` |
| "punto y coma" / "dos puntos" | `;` / `:` |
| "punto y aparte" / "nueva línea" | `.` + line break |
| "abrir paréntesis … cerrar paréntesis" | `( … )` |
| "abrir comillas … cerrar comillas" | `" … "` |
| "signo de interrogación" | `?` |
| "guion" / "barra" / "arroba" | `-` / `/` / `@` |

Disable with `dictation_commands = false` if it interferes with your natural speech.

### Custom vocabulary & corrections

Whisper recognizes your personal names and jargon much better if you teach it:

```bash
local-stt vocab add 'DevPaul' 'FastAPI' 'ydotool'   # biases transcription (initial_prompt)
local-stt correct 'dev pablo' 'DevPaul'             # fixes recurring mistakes after transcription
local-stt vocab                                      # list current terms
local-stt reload                                     # apply without restarting
```

Files: `~/.config/local-stt/vocabulary.txt` (one term per line) and `~/.config/local-stt/corrections.txt` (lines of `wrong -> right`). Corrections are word-boundary aware and preserve capitalization.

### Live OSD with voice level and partial text

While recording, a small frameless window appears at the top-center of your screen: a green voice-level bar (it moves when the mic hears you) plus the **partial transcription updating every ~1.5s as you speak**. It closes itself when you stop. Disable per-feature:

```toml
overlay = false         # no OSD at all
partial_results = false  # OSD without live text
```

Backend selection (`osd_backend = "auto" | "gtk" | "tk"`, `osd_margin_top = 80`):

| Backend | When | Requires |
|---|---|---|
| `gtk` | Wayland with layer-shell (KDE Plasma, sway/hyprland) | `gtk4`, `python-gobject`, `gtk4-layer-shell` (all in Arch `extra`; the AUR package lists them as optdepends) |
| `tk` | GNOME, X11, or if the GTK probe fails | `tk` (already installed with Python) |

The GTK backend runs as a standalone script with the **system** Python (the venv does not see PyGObject), uses the `overlay` layer anchored top-center with `keyboard_mode = none` (it never steals focus) and falls back to Tk automatically if it cannot start. `local-stt doctor` prints the chosen backend and the reason.

```bash
sudo pacman -S --needed gtk4 python-gobject gtk4-layer-shell   # native OSD
```

### Contextual vocabulary per app (optional)

Use a different vocabulary depending on which window is focused (e.g. jargon when dictating in your IDE, casual terms in a chat app):

```toml
[app_vocab]
"code|jetbrains|vscode|nvim|terminal" = "vocab-ide.txt"   # regex -> file
"whatsapp|telegram" = "vocab-chat.txt"
```

Files live in `~/.config/local-stt/` (same one-term-per-line format) and are
applied on the fly when the dictation starts. Detection chain: `kdotool`
(exact on KDE Wayland — `yay -S kdotool`) → KWin DBus (best-effort) →
`xdotool` (X11). Without any of these, the default vocabulary is used.

### Hands-free wake word (optional)

```bash
.venv/bin/pip install 'local-speech-to-text[wakeword]'   # openwakeword + onnxruntime
```

```toml
wake_word = true              # say "hey jarvis" and dictation starts
wake_word_model = "hey_jarvis"   # alexa, hey_mycroft, hey_rhasspy… or path to a custom .onnx
wake_word_threshold = 0.5
```

Runs entirely on CPU (~0% GPU). The monitor pauses while you dictate so it can't re-trigger itself. It listens continuously — turn it off (`wake_word = false` + `local-stt reload`) if you don't want an always-on microphone.

---

## Configuration

Edit `~/.config/local-stt/config.toml` (created by the installer) and run `local-stt reload`. **Environment variables always win over the TOML**, and CLI flags win over everything.

Prefer not to edit files by hand? `local-stt config` opens an interactive menu (model, language, toggles, wake word…) — press Enter to keep each value, and it never rewrites the file unless something actually changed. Without a TTY it just prints the effective config.

```toml
mic = "FaceCam"           # pin a microphone by (sub)string name; omit = system default
model = "large-v3-turbo"   # tiny, base, small, medium, large-v3, distil-large-v3
language = "es"            # "auto" for autodetection
device = "cuda"            # or "cpu"
compute_type = "float16"   # "int8_float16" = half the VRAM, minor quality loss
beam_size = 5
max_record_seconds = 120   # safety auto-stop
auto_paste = true          # send Ctrl+V automatically
dictation_commands = true  # spoken punctuation
silence_stop = false       # true = stop recording after silence_threshold_ms of silence
silence_threshold_ms = 1500
overlay = true             # floating OSD while recording
partial_results = true     # live partial transcription in the OSD
partial_interval = 1.5     # seconds between partials
# wake_word = false        # hands-free ("hey jarvis") — see above
```

Environment equivalents: `LOCAL_STT_MODEL`, `LOCAL_STT_LANG`, `LOCAL_STT_DEVICE`, `LOCAL_STT_COMPUTE`, `LOCAL_STT_BEAM`, `LOCAL_STT_MAX_SECS`, `LOCAL_STT_AUTO_PASTE`, `LOCAL_STT_DICTATION_COMMANDS`, `LOCAL_STT_SILENCE_STOP`, `LOCAL_STT_SILENCE_MS`, `LOCAL_STT_VAD`, `LOCAL_STT_VOCAB`, `LOCAL_STT_CORRECTIONS`, `LOCAL_STT_OVERLAY`, `LOCAL_STT_PARTIAL`, `LOCAL_STT_PARTIAL_SECS`, `LOCAL_STT_WAKE_WORD`, `LOCAL_STT_WAKE_MODEL`, `LOCAL_STT_WAKE_THRESHOLD`.

### Models & VRAM (RTX 5070 12GB)

| Model | VRAM (float16) | Speed | Spanish accuracy |
|---|---|---|---|
| `tiny` | ~1 GB | ⚡⚡⚡ | low |
| `small` | ~2 GB | ⚡⚡ | medium |
| `medium` | ~3 GB | ⚡ | good |
| **`large-v3-turbo`** | **~4 GB** | **⚡ 6× faster than large-v3** | **excellent — recommended** |
| `large-v3` | ~10 GB | slow | maximum |
| `distil-large-v3` | ~6 GB | ⚡ | very good (English-centric) |

Switching: change `model` in the TOML (or `LOCAL_STT_MODEL=medium`) and `local-stt reload`. The model reloads lazily on the next dictation; everything else applies instantly.

---

## How it works (architecture)

```
Win+F (khotkeys / gsettings shortcut)
  → `local-stt toggle`
      ├─ daemon down? → auto-start via systemd, wait for model, record on this keypress
      └─ unix socket /tmp/local-stt.sock → Daemon (model kept in VRAM)
            ├─ AudioRecorder   (sounddevice, 16kHz mono, RMS tracking for silence)
            ├─ Partial worker  (beam-1 re-transcription of the last 10s, feeds the OSD)
            ├─ OSD subprocess  (tkinter: voice bar + partial text, polls "level")
            ├─ Transcriber     (faster-whisper CUDA; cuBLAS 12 preloaded via ctypes)
            ├─ text_cleaner    ("punto y coma" → ";")
            ├─ corrections     (word-boundary replacements from corrections.txt)
            ├─ History         (~/.local/share/local-stt/history.jsonl, last 100)
            └─ wl-copy / xclip + notify-send + wtype Ctrl+V (auto-paste)
Wake word monitor (optional) — always-on CPU stream → "hey jarvis" → starts recording
```

- The **daemon** loads the model once and keeps it in VRAM: startup ~10s (once per login), then each transcription takes well under a second.
- **Without** the daemon every dictation would reload the model (slow). That's why the toggle auto-starts it.
- Audio flows through PipeWire/PulseAudio at 16kHz mono.
- **cuBLAS 12**: Arch ships CUDA 13 but ctranslate2 is built for CUDA 12; the pip package `nvidia-cublas-cu12` provides the missing library and `cuda_libs.py` preloads it with `ctypes.CDLL(..., RTLD_GLOBAL)` before the model loads.

---

## Troubleshooting

**`nvidia-smi` says "Driver/library version mismatch"**
- You updated `nvidia-utils` without rebooting. **Reboot.** Until then, CUDA inference may still work (the CUDA runtime doesn't use NVML), but fix it properly.
- `local-stt doctor` detects this case explicitly.

**CUDA fails with "Library libcublas.so.12 is not found or cannot be loaded"**
- Arch has CUDA 13 only; the fix ships with this repo: `.venv/bin/pip install nvidia-cublas-cu12` (it's in `pyproject.toml` and preloaded automatically). Verify with `local-stt doctor`.

**Falls back to CPU (5-10× slower)**
- Check `nvidia-smi` works and `local-stt doctor` shows a CUDA device. Reinstall drivers: `sudo pacman -S nvidia nvidia-utils`.

**Wrong microphone / doesn't record**
- `local-stt devices` to list inputs; set the default in `pavucontrol` → Input Devices.
- Debug: `arecord -l`, `pactl list sources`.

**Auto-paste doesn't work on Wayland**
- Install `wtype` (`sudo pacman -S wtype`) or `ydotool` (then `sudo systemctl enable --now ydotool`).
- Worst case the text is still in your clipboard: press `Ctrl+V` manually.

**Hotkey doesn't fire**
- KDE: log out/in once after `setup-hotkey.sh` (Plasma 6 doesn't hot-reload `khotkeysrc`), then check *System Settings → Shortcuts → Custom Shortcuts → Local STT*.
- GNOME: `gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings` should list the `custom-local-stt` entry; the command must point to the absolute path of `.venv/bin/local-stt`.

**Empty or garbage transcription**
- Speak closer to the mic; check input level in `pavucontrol`.
- Mixed languages? Set `language = "auto"` (or `"en"`).
- Test the model directly: `local-stt transcribe yourfile.wav`.

**One-command diagnosis**
- `local-stt doctor` — checks GPU driver, CUDA, cuBLAS, daemon, model cache, hotkey, clipboard tools and microphone, and tells you exactly what to fix.

---

## What's still missing (roadmap & known limitations)

Not implemented yet — documented so expectations are clear:

| Item | Status | Notes |
|---|---|---|
| **CI (GitHub Actions)** | ✅ done | `.github/workflows/ci.yml` runs the 93 unit tests (matrix 3.11/3.13) + `ruff check` on every push/PR. Slim deps (no GPU wheels): heavy imports are lazy, so tests only need `numpy` + `text2num` + `pytest`. |
| **AUR / PKGBUILD** | ✅ done | `packaging/aur/` ships a source PKGBUILD (AUR deps for the Python stack, cuBLAS 12 bundled from the PyPI wheel into `/usr/lib/local-stt/cublas`). Uninstall via `pacman -R local-stt`; `local-stt uninstall` stays user-level only. |
| **Push-to-talk (hold key)** | ✅ done | `push_to_talk = true` + `python-evdev`: hold `Win+F` to record, release to transcribe. Opt-in because it needs read access to `/dev/input` (grupo `input`). See [Push-to-talk](#push-to-talk-hold-to-dictate). |
| **Custom Spanish wake word** | ❌ | openWakeWord ships English-trained models ("hey jarvis", "alexa"…). A custom "oye computadora" requires training a model (synthetic TTS data + fine-tune). |
| **Wayland-native OSD** | ✅ KDE/wlroots, Tk on GNOME | `gtk4` + `python-gobject` + `gtk4-layer-shell`: floating indicator on the `overlay` layer, no XWayland and no focus stealing. GNOME/Mutter has no layer-shell, so it keeps the Tk/XWayland OSD. See [Live OSD](#live-osd-with-voice-level-and-partial-text). |
| **Exact window detection on KDE** | partial | Requires `kdotool` (AUR). The built-in KWin DBus fallback works but is best-effort and slower (see *Contextual vocabulary*). |
| **Multi-language output** | ❌ | Whisper's `task=translate` only translates **into English**. Dictating Spanish → English works; the reverse doesn't exist upstream. |

Also note: `local-stt history` and `pick` show the *raw* saved text; entries
saved before a config change (e.g. enabling `numbers_to_digits`) are not
re-processed.

---

## Uninstall

```bash
# Instalado vía AUR:
sudo pacman -R local-stt                          # archivos del sistema
local-stt uninstall --yes --purge                  # servicio + atajos + config + historial

# Instalado vía clone + install.sh:
.venv/bin/local-stt uninstall --yes --purge        # lo anterior + .venv del repo
# sin --purge: conserva tus datos por si vuelves
```

## Development

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest tests/ -q
```

Pure-Python logic (text cleaning, config layering, vocabulary, corrections, OSD protocol, push-to-talk state machine) is unit-tested; GPU/daemon paths are covered by `local-stt doctor` and an end-to-end toggle.

CI (`.github/workflows/ci.yml`) runs four jobs: `test` (Python 3.11/3.13/3.14, slim deps; audio/GPU tests skip), `lint` (ruff), `build` (wheel + `python-installer`, the same path as the AUR package) and `audio` (PortAudio installed, so recorder tests run for real).

## License

MIT
