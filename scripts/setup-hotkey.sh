#!/usr/bin/env bash
# Configura Win+F como atajo global en GNOME (Wayland) que llama a `local-stt toggle`
# Uso: ./scripts/setup-hotkey.sh
set -euo pipefail

BIN="$(command -v local-stt || echo "$HOME/.local/bin/local-stt")"
if [[ ! -x "$BIN" && ! -x "$HOME/.local/bin/local-stt" ]]; then
  echo "⚠️  No se encontró 'local-stt' en PATH. Instala primero con ./scripts/install.sh"
  echo "   Intentando con: $BIN"
fi
# Si está en venv, usa esa ruta
if [[ -x ".venv/bin/local-stt" ]]; then
  BIN="$(pwd)/.venv/bin/local-stt"
fi

echo "→ Configurando atajo Super+F -> $BIN toggle"

# GNOME custom keybindings via gsettings
# Creamos/actualizamos entrada custom0 (preservando existentes)
EXISTING=$(gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings 2>/dev/null || echo "@as []")
echo "   Atajos existentes: $EXISTING"

TARGET="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom-local-stt/"
# Añadir a la lista si no existe
if ! echo "$EXISTING" | grep -q "custom-local-stt"; then
  # extraer lista actual y añadir
  if [[ "$EXISTING" == "@as []" || "$EXISTING" == "[]" ]]; then
    NEW_LIST="['$TARGET']"
  else
    # insertar antes del ]
    NEW_LIST=$(echo "$EXISTING" | sed "s/]$/, '$TARGET']/")
  fi
  gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "$NEW_LIST"
  echo "   Lista actualizada: $NEW_LIST"
fi

gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:"$TARGET" name 'Local STT Dictado'
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:"$TARGET" command "$BIN toggle"
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:"$TARGET" binding '<Super>f'

echo "✅ Atajo configurado: Super+F -> $BIN toggle"
echo "   Prueba: presiona Win+F. Si no funciona, revisa Configuración > Teclado > Atajos personalizados."

# KDE: instruccion alternativa
if [[ "$XDG_CURRENT_DESKTOP" == *"KDE"* ]]; then
  echo ""
  echo "KDE detectado: configura manualmente en Preferencias > Atajos > Añadir comando: $BIN toggle -> Meta+F"
fi
