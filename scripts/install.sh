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

echo "→ Instalando paquete + deps..."
pip install -e .

# Verificar CUDA
echo ""
echo "→ Verificando GPU..."
if command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null; then
  nvidia-smi --query-gpu=name,memory.total --format=csv
  echo "   GPU detectada. Modelo large-v3-turbo usará ~3-4GB VRAM en float16."
else
  echo "⚠️  nvidia-smi no disponible ahora. En tu máquina con RTX 5070 debería aparecer."
  echo "   Si usas CUDA, asegúrate de tener nvidia-drivers + cuda 12.8+ instalados."
  echo "   El daemon hará fallback a CPU si no hay GPU."
fi

echo ""
echo "→ Probando import..."
python -c "import sounddevice; print('sounddevice OK:', sounddevice.query_devices().__str__()[:200])" || echo "   sounddevice fallo (normal si no hay audio en este entorno)"
python -c "import faster_whisper; print('faster-whisper OK')" || echo "   faster-whisper no instalado? revisa pip"

echo ""
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
Environment=LOCAL_STT_MODEL=large-v3-turbo
Environment=LOCAL_STT_DEVICE=cuda
Environment=LOCAL_STT_COMPUTE=float16

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload || true

echo ""
echo "✅ Instalación base completa."
echo ""
echo "Próximos pasos:"
echo "  1. Configurar atajo Win+F:  ./scripts/setup-hotkey.sh"
echo "  2. Iniciar daemon:         .venv/bin/local-stt daemon"
echo "     (o como servicio:       systemctl --user enable --now local-stt)"
echo "  3. Presiona Win+F, habla, Win+F de nuevo -> se copia y pega con Ctrl+V"
echo "  4. Listar micros:          .venv/bin/local-stt devices"
echo "  5. Probar archivo:         .venv/bin/local-stt transcribe audio.wav --copy"
echo ""
echo "Tips RTX 5070:"
echo "  - Modelos: tiny(1GB) < base < small < medium(5GB) < large-v3-turbo(6GB, recomendado) < large-v3(10GB)"
echo "  - Si VRAM justa, usa: LOCAL_STT_MODEL=medium LOCAL_STT_COMPUTE=int8_float16"
echo "  - Cambia idioma: LOCAL_STT_LANG=en  o  auto para autodetectar"
