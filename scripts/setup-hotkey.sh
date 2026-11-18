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

  # Grupo Data: dictado (opcional) + historial. Con push-to-talk el listener
  # evdev es dueño de Win+F, así que el compositor solo registra historial.
  kwriteconfig6 --file khotkeysrc --group Data --key DataCount \
    "$([[ "${LOCAL_STT_SKIP_TOGGLE:-0}" == "1" ]] && echo 1 || echo 2)" 2>/dev/null || true

  kde_action() {
    local idx="$1" name="$2" command="$3" key="$4" uuid="$5"
    kwriteconfig6 --file khotkeysrc --group "Data_$idx" --key Comment "$name" 2>/dev/null || true
    kwriteconfig6 --file khotkeysrc --group "Data_$idx" --key Enabled true 2>/dev/null || true
    kwriteconfig6 --file khotkeysrc --group "Data_$idx" --key Name "$name" 2>/dev/null || true
    kwriteconfig6 --file khotkeysrc --group "Data_$idx" --key Type "SIMPLE_ACTION_DATA" 2>/dev/null || true
    kwriteconfig6 --file khotkeysrc --group "Data_${idx}Actions" --key ActionsCount 1 2>/dev/null || true
    kwriteconfig6 --file khotkeysrc --group "Data_${idx}Actions0" --key CommandURL "$command" 2>/dev/null || true
    kwriteconfig6 --file khotkeysrc --group "Data_${idx}Actions0" --key Type "COMMAND_URL" 2>/dev/null || true
    kwriteconfig6 --file khotkeysrc --group "Data_${idx}Conditions" --key ConditionsCount 0 2>/dev/null || true
    kwriteconfig6 --file khotkeysrc --group "Data_${idx}Conditions" --key Comment "" 2>/dev/null || true
    kwriteconfig6 --file khotkeysrc --group "Data_${idx}Triggers" --key TriggersCount 1 2>/dev/null || true
    kwriteconfig6 --file khotkeysrc --group "Data_${idx}Triggers0" --key Key "$key" 2>/dev/null || true
    kwriteconfig6 --file khotkeysrc --group "Data_${idx}Triggers0" --key Type "SHORTCUT" 2>/dev/null || true
    kwriteconfig6 --file khotkeysrc --group "Data_${idx}Triggers0" --key Uuid "$uuid" 2>/dev/null || true
  }

  if [[ "${LOCAL_STT_SKIP_TOGGLE:-0}" == "1" ]]; then
    kde_action 1 "Local STT Historial (Win+Shift+F)" "$BIN pick" "Meta+Shift+F" "$UUID-pick"
    echo "   Push-to-talk: Win+F lo gestiona el daemon (listener evdev)"
  else
    kde_action 1 "Local STT Dictado (Win+F)" "$BIN toggle" "Meta+F" "$UUID"
    kde_action 2 "Local STT Historial (Win+Shift+F)" "$BIN pick" "Meta+Shift+F" "$UUID-pick"
  fi

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
  if [[ "${LOCAL_STT_SKIP_TOGGLE:-0}" == "1" ]]; then
    echo "✅ Atajo KDE: Win+Shift+F -> historial (Win+F lo gestiona push-to-talk)"
  else
    echo "✅ Atajos KDE configurados: Meta+F -> dictado | Meta+Shift+F -> historial"
  fi
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
    if [[ "${LOCAL_STT_SKIP_TOGGLE:-0}" == "1" && "$TARGET" == *"/custom-local-stt/" ]]; then
      # push-to-talk: el listener evdev es dueño de Win+F
      gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:"$TARGET" binding "" 2>/dev/null || true
      echo "   Push-to-talk: atajo de dictado desactivado en GNOME"
      continue
    fi
    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:"$TARGET" binding "$BINDING"
  done

  echo ""
  if [[ "${LOCAL_STT_SKIP_TOGGLE:-0}" == "1" ]]; then
    echo "✅ Atajos GNOME: Win+F -> push-to-talk (evdev) | Win+Shift+F -> historial"
  else
    echo "✅ Atajos GNOME configurados: Super+F -> dictado | Super+Shift+F -> historial"
  fi
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
