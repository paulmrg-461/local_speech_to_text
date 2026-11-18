#!/usr/bin/env bash
# Instalador para RTX 5070 12GB - Local STT con faster-whisper CUDA
set -euo pipefail
echo "== Local STT Installer (RTX 5070 + Wayland) =="

# 1. Dependencias sistema (Arch/EndeavourOS)
echo "→ Instalando deps sistema..."
if command -v pacman &>/dev/null; then
  sudo pacman -S --needed --noconfirm \
    python-pip python-virtualenv portaudio \
    wl-clipboard libnotify \
    wtype ydotool 2>/dev/null || true
  # alternativas si wtype/ydotool no están en repos oficiales
  if ! command -v wtype &>/dev/null; then
    echo "   wtype no encontrado en repos, intenta: yay -S wtype"
  fi
  if ! command -v wl-copy &>/dev/null; then
    sudo pacman -S --needed wl-clipboard
  fi
else
  echo "No es Arch, instala manualmente: portaudio, wl-clipboard, wtype, libnotify"
fi

# 2. Entorno Python
echo "→ Creando venv..."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip wheel

echo "→ Instalando paquete + deps (incluye nvidia-cublas-cu12 para CUDA en Arch)..."
pip install -e .

# Verificar CUDA
echo ""
echo "→ Verificando GPU..."
if command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null; then
  nvidia-smi --query-gpu=name,memory.total --format=csv
  echo "   GPU detectada. Modelo large-v3-turbo usará ~3-4GB VRAM en float16."
else
  echo "⚠️  nvidia-smi no disponible ahora. En tu máquina con RTX 5070 debería aparecer."
  echo "   Si actualizaste nvidia-utils hace poco: REINICIA el equipo."
  echo "   El daemon hará fallback a CPU si no hay GPU."
fi

echo ""
echo "→ Probando import..."
python -c "import sounddevice; print('sounddevice OK:', sounddevice.query_devices().__str__()[:200])" || echo "   sounddevice fallo (normal si no hay audio en este entorno)"
python -c "import faster_whisper; print('faster-whisper OK')" || echo "   faster-whisper no instalado? revisa pip"

# Config editable: ~/.config/local-stt/config.toml (env sigue ganando)
echo "→ Escribiendo config ~/.config/local-stt/config.toml..."
mkdir -p ~/.config/local-stt
CFG=~/.config/local-stt/config.toml
if [[ ! -f "$CFG" ]]; then
cat > "$CFG" <<EOF
# Config de local-stt (el entorno LOCAL_STT_* gana sobre este archivo)
# Modelos: tiny, base, small, medium, large-v3, large-v3-turbo, distil-large-v3
model = "large-v3-turbo"   # sweet spot RTX 5070 12GB
language = "es"            # "auto" para autodetectar
device = "cuda"
compute_type = "float16"
beam_size = 5
max_record_seconds = 120
auto_paste = true
dictation_commands = true  # "punto y coma" -> ;  "nueva línea" -> salto
silence_stop = false       # true: para solo tras 1.5s de silencio (manos libres)
silence_threshold_ms = 1500
overlay = true             # OSD flotante con nivel de voz mientras grabas
partial_results = true     # texto parcial en vivo dentro del OSD
partial_interval = 1.5     # segundos entre parciales
EOF
else
  echo "   ya existe, no se toca"
fi

echo "→ Instalando servicio systemd --user..."
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/local-stt.service <<EOF
[Unit]
Description=Local STT Daemon (RTX 5070) - Win+F dictado
After=graphical-session.target pipewire.service

[Service]
Type=simple
ExecStart=$(pwd)/.venv/bin/local-stt daemon
Restart=on-failure
RestartSec=3
# Opcional: overrides de entorno (ganan sobre config.toml)
EnvironmentFile=-%h/.config/local-stt/config.env

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload || true

# Pre-descargar el modelo para que el primer dictado no espere
echo ""
echo "→ Pre-descargando modelo (una sola vez, ~1.5GB)..."
"$(pwd)/.venv/bin/local-stt" download || echo "   ⚠️  descarga falló: se descargará al primer uso"

echo ""
echo "✅ Instalación base completa."
echo ""
echo "Próximos pasos:"
echo "  1. Configurar atajo Win+F:  ./scripts/setup-hotkey.sh"
echo "  2. Iniciar daemon:         systemctl --user enable --now local-stt"
echo "     (o probar en foreground: .venv/bin/local-stt daemon)"
echo "  3. Diagnóstico completo:   .venv/bin/local-stt doctor"
echo "  4. Presiona Win+F, habla, Win+F de nuevo -> se copia y pega con Ctrl+V"
echo ""
echo "Cambiar modelo/idioma: edita ~/.config/local-stt/config.toml y reinicia:"
echo "  systemctl --user restart local-stt"
