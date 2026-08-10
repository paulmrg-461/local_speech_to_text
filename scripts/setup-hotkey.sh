#!/usr/bin/env bash
# Configura Win+F (Super/Meta+F) para `local-stt toggle`
# Default: KDE Plasma 6 (khotkeysrc + kglobalaccel). GNOME opcional via env var.
#
# Uso:
#   ./scripts/setup-hotkey.sh              # default KDE
#   ./scripts/setup-hotkey.sh --kde        # fuerza KDE
#   ./scripts/setup-hotkey.sh --gnome      # fuerza GNOME
#   LOCAL_STT_DESKTOP=gnome ./scripts/setup-hotkey.sh
#   LOCAL_STT_DESKTOP=kde ./scripts/setup-hotkey.sh
#   LOCAL_STT_DESKTOP=auto ./scripts/setup-hotkey.sh   # autodetecta XDG_CURRENT_DESKTOP
#
set -euo pipefail

BIN="$(command -v local-stt 2>/dev/null || echo "$HOME/.local/bin/local-stt")"
if [[ ! -x "$BIN" && ! -x "$HOME/.local/bin/local-stt" ]]; then
  echo "⚠️  No se encontró 'local-stt' en PATH. Instala primero con ./scripts/install.sh"
  echo "   Intentando con: $BIN"
fi
if [[ -x ".venv/bin/local-stt" ]]; then
  BIN="$(pwd)/.venv/bin/local-stt"
fi
# Ruta absoluta para KDE (khotkeys no expande relativo)
BIN="$(realpath -m "$BIN" 2>/dev/null || echo "$BIN")"

# --- Selección de backend ---
# Default: KDE. Permite override via env var o flag CLI.
BACKEND="${LOCAL_STT_DESKTOP:-kde}"
BACKEND="${BACKEND,,}"  # lowercase

for arg in "$@"; do
  case "$arg" in
    --kde) BACKEND="kde" ;;
    --gnome) BACKEND="gnome" ;;
    --auto) BACKEND="auto" ;;
  esac
done

if [[ "$BACKEND" == "auto" ]]; then
  if [[ "${XDG_CURRENT_DESKTOP:-}" == *"GNOME"* ]]; then
    BACKEND="gnome"
  else
    BACKEND="kde"
  fi
fi

if [[ "$BACKEND" != "kde" && "$BACKEND" != "gnome" ]]; then
  echo "Valor LOCAL_STT_DESKTOP inválido: $BACKEND (usa kde|gnome|auto)"
  exit 1
fi

echo "→ Backend: $BACKEND | Atajo: Super/Meta+F -> $BIN toggle"
echo ""

# ===================== KDE Plasma 6 =====================
setup_kde() {
  echo "→ Configurando KDE Plasma 6 (khotkeysrc + kglobalaccel)..."

  if ! command -v kwriteconfig6 &>/dev/null; then
    echo "❌ kwriteconfig6 no encontrado. ¿Estás en KDE Plasma 6?"
    echo "   Alternativa manual: Ajustes del sistema → Atajos → Atajos personalizados → Añadir → Orden/URL"
    echo "   Orden: $BIN toggle  |  Activador: Meta+F"
    return 1
  fi

  local KHOTKEYSRC
  KHOTKEYSRC="${XDG_CONFIG_HOME:-$HOME/.config}/khotkeysrc"
  local UUID="local-stt-toggle-$(echo -n "$BIN" | md5sum | cut -c1-8)"

  # Grupo Data: entrada principal (ignora error en sandbox RO, se verifica luego)
  kwriteconfig6 --file khotkeysrc --group Data --key DataCount 1 2>/dev/null || true

  kwriteconfig6 --file khotkeysrc --group Data_1 --key Comment "Local STT Dictado (Win+F)" 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_1 --key Enabled true 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_1 --key Name "Local STT" 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_1 --key Type "SIMPLE_ACTION_DATA" 2>/dev/null || true

  # Acción: ejecutar comando
  kwriteconfig6 --file khotkeysrc --group Data_1Actions --key ActionsCount 1 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_1Actions0 --key CommandURL "$BIN toggle" 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_1Actions0 --key Type "COMMAND_URL" 2>/dev/null || true

  # Condiciones vacías
  kwriteconfig6 --file khotkeysrc --group Data_1Conditions --key ConditionsCount 0 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_1Conditions --key Comment "" 2>/dev/null || true

  # Trigger: Meta+F
  kwriteconfig6 --file khotkeysrc --group Data_1Triggers --key TriggersCount 1 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_1Triggers0 --key Key "Meta+F" 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_1Triggers0 --key Type "SHORTCUT" 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_1Triggers0 --key Uuid "$UUID" 2>/dev/null || true

  if [[ ! -f "$KHOTKEYSRC" ]]; then
    echo "❌ No se pudo escribir $KHOTKEYSRC (¿sistema de archivos de solo lectura? Ejecuta fuera del sandbox/contenedor)"
    return 1
  fi
  echo "   Escrito: $KHOTKEYSRC"

  # Recargar atajos (Plasma 6 no expone reconfigure; el cambio se aplica al reiniciar sesión)
  if command -v qdbus6 &>/dev/null; then
    qdbus6 org.kde.kglobalaccel /kglobalaccel org.kde.KGlobalAccel.reconfigure >/dev/null 2>&1 || true
    qdbus6 org.kde.khotkeys /khotkeys org.kde.khotkeys.reconfigure >/dev/null 2>&1 || true
    qdbus6 org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true
  fi
  echo "   Nota: en Plasma 6 puede que necesites cerrar sesión y volver a entrar para que aparezca."
  echo "   Alternativa: kquitapp6 kglobalaccel && kglobalaccel6 &  (o reinicia)"

  echo ""
  echo "✅ Atajo KDE configurado: Meta+F -> $BIN toggle"
  echo "   Verifica en: Ajustes del sistema → Atajos → Atajos personalizados → Local STT"
  echo "   Prueba: presiona Win+F. Si no funciona, reasigna el activador a Meta+F manualmente."
}

# ===================== GNOME =====================
setup_gnome() {
  echo "→ Configurando GNOME (gsettings)..."

  if ! command -v gsettings &>/dev/null; then
    echo "❌ gsettings no encontrado. ¿Estás en GNOME?"
    echo "   Alternativa manual: Configuración → Teclado → Atajos personalizados → +"
    echo "   Nombre: Local STT | Orden: $BIN toggle | Atajo: Super+F"
    return 1
  fi

  local EXISTING
  EXISTING=$(gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings 2>/dev/null || echo "@as []")
  echo "   Atajos existentes: $EXISTING"

  local TARGET="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom-local-stt/"
  if ! echo "$EXISTING" | grep -q "custom-local-stt"; then
    local NEW_LIST
    if [[ "$EXISTING" == "@as []" || "$EXISTING" == "[]" ]]; then
      NEW_LIST="['$TARGET']"
    else
      NEW_LIST=$(echo "$EXISTING" | sed "s/]$/, '$TARGET']/")
    fi
    gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "$NEW_LIST"
    echo "   Lista actualizada: $NEW_LIST"
  fi

  gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:"$TARGET" name 'Local STT Dictado'
  gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:"$TARGET" command "$BIN toggle"
  gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:"$TARGET" binding '<Super>f'

  echo ""
  echo "✅ Atajo GNOME configurado: Super+F -> $BIN toggle"
  echo "   Prueba: presiona Win+F. Si no funciona, revisa Configuración → Teclado → Atajos personalizados."
}

# --- Dispatch ---
case "$BACKEND" in
  kde) setup_kde || exit 1 ;;
  gnome) setup_gnome || exit 1 ;;
esac

echo ""
echo "Tip: fuerza el otro backend con:"
echo "  LOCAL_STT_DESKTOP=gnome ./scripts/setup-hotkey.sh   # para GNOME"
echo "  LOCAL_STT_DESKTOP=kde ./scripts/setup-hotkey.sh     # para KDE (default)"
