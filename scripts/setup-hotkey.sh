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

  # Grupo Data: dos acciones (dictado e historial) (ignora error en sandbox RO)
  kwriteconfig6 --file khotkeysrc --group Data --key DataCount 2 2>/dev/null || true

  # ---- Acción 1: dictado (Meta+F -> toggle) ----
  kwriteconfig6 --file khotkeysrc --group Data_1 --key Comment "Local STT Dictado (Win+F)" 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_1 --key Enabled true 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_1 --key Name "Local STT" 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_1 --key Type "SIMPLE_ACTION_DATA" 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_1Actions --key ActionsCount 1 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_1Actions0 --key CommandURL "$BIN toggle" 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_1Actions0 --key Type "COMMAND_URL" 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_1Conditions --key ConditionsCount 0 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_1Conditions --key Comment "" 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_1Triggers --key TriggersCount 1 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_1Triggers0 --key Key "Meta+F" 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_1Triggers0 --key Type "SHORTCUT" 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_1Triggers0 --key Uuid "$UUID" 2>/dev/null || true

  # ---- Acción 2: selector de historial (Meta+Shift+F -> pick) ----
  kwriteconfig6 --file khotkeysrc --group Data_2 --key Comment "Local STT Historial (Win+Shift+F)" 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_2 --key Enabled true 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_2 --key Name "Local STT Historial" 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_2 --key Type "SIMPLE_ACTION_DATA" 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_2Actions --key ActionsCount 1 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_2Actions0 --key CommandURL "$BIN pick" 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_2Actions0 --key Type "COMMAND_URL" 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_2Conditions --key ConditionsCount 0 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_2Conditions --key Comment "" 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_2Triggers --key TriggersCount 1 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_2Triggers0 --key Key "Meta+Shift+F" 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_2Triggers0 --key Type "SHORTCUT" 2>/dev/null || true
  kwriteconfig6 --file khotkeysrc --group Data_2Triggers0 --key Uuid "$UUID-pick" 2>/dev/null || true

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
  echo "✅ Atajos KDE configurados: Meta+F -> dictado | Meta+Shift+F -> historial"
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

  for TARGET in \
    "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom-local-stt/" \
    "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom-local-stt-pick/"; do
    if ! echo "$EXISTING" | grep -q "$(basename "$TARGET")"; then
      local NEW_LIST
      if [[ "$EXISTING" == "@as []" || "$EXISTING" == "[]" ]]; then
        NEW_LIST="['$TARGET']"
      else
        NEW_LIST=$(echo "$EXISTING" | sed "s/]$/, '$TARGET']/")
      fi
      gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "$NEW_LIST"
      EXISTING="$NEW_LIST"
      echo "   Añadido: $TARGET"
    fi

    local NAME COMMAND BINDING
    if [[ "$TARGET" == *"-pick/" ]]; then
      NAME='Local STT Historial'; COMMAND="$BIN pick"; BINDING='<Super><shift>f'
    else
      NAME='Local STT Dictado'; COMMAND="$BIN toggle"; BINDING='<Super>f'
    fi
    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:"$TARGET" name "$NAME"
    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:"$TARGET" command "$COMMAND"
    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:"$TARGET" binding "$BINDING"
  done

  echo ""
  echo "✅ Atajos GNOME configurados: Super+F -> dictado | Super+Shift+F -> historial"
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
