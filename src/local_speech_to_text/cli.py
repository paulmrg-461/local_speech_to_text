from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .config import Config
from .daemon import Daemon, send_command
from .recorder import AudioRecorder

SERVICE = "local-stt.service"
# Instalación empaquetada (pacman/AUR): binario y assets fuera del repo.
SHARE_DIR = Path("/usr/share/local-stt")
SYSTEM_UNIT_DIR = Path("/usr/lib/systemd/user")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _hotkey_script(repo_root: Path | None = None, share_dir: Path | None = None) -> Path | None:
    """setup-hotkey.sh del repo (venv) o de /usr/share/local-stt (pacman/AUR)."""
    bases = ((repo_root or _repo_root()) / "scripts", share_dir or SHARE_DIR)
    for base in bases:
        script = base / "setup-hotkey.sh"
        if script.exists():
            return script
    return None


def _user_unit() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / SERVICE


def _system_unit(system_dir: Path | None = None) -> Path:
    return (system_dir or SYSTEM_UNIT_DIR) / SERVICE


def _service_installed(user_unit: Path | None = None, system_unit: Path | None = None) -> bool:
    """True si el unit existe en ~/.config (venv) o en /usr/lib (paquete)."""
    return (user_unit or _user_unit()).exists() or (system_unit or _system_unit()).exists()


def _config_from_args(args) -> Config:
    """Config final: CLI (solo si se pasó) > env > TOML > defaults."""
    lang = None if getattr(args, "lang", "es") == "auto" else getattr(args, "lang", "es")
    return Config.load(
        model=getattr(args, "model", None),
        language=lang,
        device=getattr(args, "device", None),
        compute_type=getattr(args, "compute", None),
    )


def _autostart_daemon(cfg: Config) -> bool:
    """Arranca el daemon: systemd --user si existe el unit, si no proceso suelto.

    Espera a que el socket esté listo para que el mismo Win+F que lo arrancó
    empiece a grabar (o como mucho muestre que el modelo está cargando).
    """
    try:
        if _service_installed():
            subprocess.run(
                ["systemctl", "--user", "start", SERVICE],
                check=True, timeout=10,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            cfg.log_dir.mkdir(parents=True, exist_ok=True)
            log = open(cfg.log_dir / "daemon.log", "ab")
            subprocess.Popen(
                [sys.executable, "-m", "local_speech_to_text.cli", "daemon"],
                stdout=log, stderr=log, start_new_session=True,
            )
    except Exception as e:
        print(f"No se pudo arrancar el daemon: {e}")
        return False

    print("Daemon iniciando (primera vez carga el modelo ~10-25s)...")
    for _ in range(60):  # hasta 30s
        if cfg.socket_path.exists():
            return True
        time.sleep(0.5)
    print("El daemon no respondió en 30s. Revisa: local-stt doctor")
    return False


def cmd_daemon(args):
    d = Daemon(_config_from_args(args))
    d.start()


def cmd_toggle(args):
    cfg = _config_from_args(args)
    resp = send_command("toggle", cfg.socket_path)
    if "no corre" in resp:
        from .clipboard import notify

        notify("Local STT", "Daemon apagado: arrancando con el modelo, espera la notificación...")
        if _autostart_daemon(cfg):
            resp = send_command("toggle", cfg.socket_path)
    print(resp)


def cmd_status(args):
    resp = send_command("status", _config_from_args(args).socket_path)
    print(resp)


def cmd_osd(args):
    """Estado del OSD: backend elegido, disponibilidad y cómo habilitarlo."""
    from .osd_backend import describe, find_system_python, gtk_layer_available, select_backend

    cfg = _config_from_args(args)
    backend, reason = select_backend(cfg.osd_backend)
    print(f"OSD: {describe(backend, reason)}")
    print(f"python del sistema: {find_system_python() or 'no encontrado'}")
    available = True
    if backend == "gtk":
        available = gtk_layer_available()
        print("GTK4 + gtk4-layer-shell:", "sí" if available else "no")
        if not available:
            print("  sudo pacman -S --needed gtk4 python-gobject gtk4-layer-shell")
    print(f"overlay: {'on' if cfg.overlay else 'off'} · margen: {cfg.osd_margin_top}px")
    if getattr(args, "preview", False):
        if backend == "gtk" and not available:
            print("No puedo previsualizar GTK: instala las dependencias de arriba.")
            sys.exit(1)
        seconds = float(getattr(args, "seconds", 6.0))
        if backend == "gtk":
            argv = [
                find_system_python() or "python3",
                str(Path(__file__).with_name("osd_gtk.py")),
                "--preview", "--seconds", str(seconds),
            ]
        else:
            argv = [
                sys.executable, "-m", "local_speech_to_text.osd",
                "--preview", "--seconds", str(seconds),
            ]
        print(f"Vista previa del OSD ({backend}, {seconds:g}s)...")
        subprocess.run(argv, timeout=seconds + 5)
        return
    if getattr(args, "check", False):
        sys.exit(0 if available else 1)


def cmd_stop(args):
    resp = send_command("quit", _config_from_args(args).socket_path)
    print(resp)


def cmd_reload(args):
    """Recarga config (TOML/env) sin reiniciar el daemon. Cambia modelo/idioma al vuelo."""
    resp = send_command("reload", _config_from_args(args).socket_path)
    print(resp)


def cmd_translate(args):
    """Alterna modo traducción: dicta en tu idioma, sale en inglés."""
    resp = send_command("translate", _config_from_args(args).socket_path)
    print(resp)


def cmd_devices(args):
    print(AudioRecorder.list_devices())


def cmd_history(args):
    """Muestra las últimas transcripciones. `--copy N` copia la N-ésima (1=última)."""
    cfg = _config_from_args(args)
    if not cfg.history_path.exists():
        print("Sin historial todavía. Dicta algo primero (Win+F).")
        return
    entries = [json.loads(ln) for ln in cfg.history_path.read_text().splitlines() if ln.strip()]
    if not entries:
        print("Historial vacío.")
        return
    entries = entries[-args.count:]
    if args.copy:
        idx = args.copy if args.copy > 0 else 1
        if idx > len(entries):
            print(f"Solo hay {len(entries)} entradas.")
            sys.exit(1)
        from .clipboard import copy_to_clipboard

        copy_to_clipboard(entries[-idx]["text"])
        print(f"Copiada (última #{idx}): {entries[-idx]['text'][:120]}")
        return
    for i, e in enumerate(reversed(entries), 1):
        print(f"#{i:<3} {e['ts']}  {e['text'][:100]}")


def cmd_download(args):
    """Pre-descarga el modelo a ~/.cache/huggingface (sin tocar la GPU)."""
    from .clipboard import notify

    cfg = _config_from_args(args)
    print(f"Descargando modelo {cfg.model} (solo la primera vez)...")
    try:
        from faster_whisper.utils import download_model

        path = download_model(cfg.model)
        print(f"✅ Modelo listo en: {path}")
        notify("Local STT", f"Modelo {cfg.model} descargado")
    except Exception as e:
        print(f"❌ Descarga fallida: {e}")
        sys.exit(1)


def cmd_vocab(args):
    """Gestiona el vocabulario (initial_prompt de Whisper): list / add / remove."""
    from .vocab import load_vocabulary

    cfg = _config_from_args(args)
    path = cfg.vocabulary_file
    terms = [t for t in load_vocabulary(path).split(", ") if t] if path.exists() else []
    if args.action == "add":
        for t in args.terms:
            if t not in terms:
                terms.append(t)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(terms) + "\n")
        print(f"✅ Vocabulario guardado ({len(terms)} términos): {path}")
    elif args.action == "remove":
        terms = [t for t in terms if t not in args.terms]
        path.write_text("\n".join(terms) + "\n" if terms else "")
        print(f"✅ Vocabulario guardado ({len(terms)} términos): {path}")
    else:
        if not terms:
            print("Vocabulario vacío. Añade con: local-stt vocab add 'DevPaul' 'FastAPI'")
        else:
            print(f"Vocabulario ({len(terms)}) → {path}")
            print("  " + "\n  ".join(terms))


def cmd_correct(args):
    """Añade una corrección: `local-stt correct 'de esto' 'a esto'`."""
    cfg = _config_from_args(args)
    path = cfg.corrections_file
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(f"{args.wrong} -> {args.right}\n")
    print(f"✅ Corrección guardada: '{args.wrong}' → '{args.right}' en {path}")


def _check(ok: bool, label: str, ok_msg: str, err: str, warn: bool = False) -> bool:
    icon = "✅" if ok else ("⚠️ " if warn else "❌")
    print(f"{icon} {label}: {ok_msg if ok else err}")
    return ok or warn


def _pick_tool() -> str | None:
    """Devuelve el selector disponible: wofi (Wayland) o rofi (fallback)."""
    import shutil

    return next((t for t in ("wofi", "rofi") if shutil.which(t)), None)


def cmd_pick(args):
    """Abre wofi/rofi con las últimas transcripciones; la elegida se copia y pega."""
    import subprocess as sp

    cfg = _config_from_args(args)
    if not cfg.history_path.exists():
        print("Sin historial todavía. Dicta algo primero (Win+F).")
        sys.exit(1)
    entries = [json.loads(ln) for ln in cfg.history_path.read_text().splitlines() if ln.strip()]
    if not entries:
        print("Historial vacío.")
        sys.exit(1)
    entries = entries[-args.count:]

    tool = _pick_tool()
    if tool is None:
        print("❌ Falta wofi o rofi. Instala con: sudo pacman -S wofi")
        sys.exit(1)

    # mostramos la más reciente arriba; wofi devuelve el índice en la 1ª línea
    lines = [e["text"].replace("\n", " ⏎ ") for e in reversed(entries)]
    dmenu = sp.run(
        [tool, "--dmenu", "-i", "-p", "Local STT · dictados"],
        input="\n".join(lines), capture_output=True, text=True,
        env={**os.environ, "_lines_count": str(len(lines))},
    )
    if dmenu.returncode != 0 or not dmenu.stdout.strip():
        print("Cancelado.")
        return
    chosen = lines.index(dmenu.stdout.strip("\n"))
    text = entries[-(chosen + 1)]["text"]

    from .clipboard import copy_to_clipboard, notify, paste_via_key

    copy_to_clipboard(text)
    print(f"✅ {text[:120]}")
    if args.paste:
        time.sleep(0.15)
        if paste_via_key():
            print("(pegado con Ctrl+V)")
    else:
        notify("Copiado", text[:120], icon="edit-paste")


_SYSTEM_DEPS = (
    # (binario, paquete pacman, para qué sirve)
    ("wl-copy", "wl-clipboard", "copiar al portapapeles (Wayland)"),
    ("wl-paste", "wl-clipboard", "verificar el clipboard"),
    ("wtype", "wtype", "auto-pegar Ctrl+V (Wayland)"),
    ("notify-send", "libnotify", "notificaciones"),
    ("wofi", "wofi", "selector de historial (Win+Shift+F)"),
    ("canberra-gtk-play", "libcanberra", "sonidos de inicio/fin"),
    ("kdotool", "kdotool (AUR)", "detección exacta de ventana para vocabulario por app"),
)


def _check_system_deps() -> bool:
    """Retorna True si falta algo; imprime el comando de instalación agrupado."""
    import shutil

    missing = [(bin_, pkg, why) for bin_, pkg, why in _SYSTEM_DEPS if not shutil.which(bin_)]
    if not missing:
        return False
    print("\n⚠️  Dependencias de sistema opcionales/faltantes:")
    for bin_, pkg, why in missing:
        print(f"   {bin_:<20} {why}")
    oficial = [p for _, p, _ in missing if "AUR" not in p]
    if oficial:
        print(f"\n   Instálalas con:\n   sudo pacman -S --needed {' '.join(dict.fromkeys(oficial))}")
    aur = [p for _, p, _ in missing if "AUR" in p]
    if aur:
        print(f"   Opcional vía AUR: yay -S {' '.join(p.split(' ')[0] for p in aur)}")
    return True


def _input_group_ok(group_ids: list[int] | None = None, input_gid: int | None = None) -> bool:
    """True si el proceso puede leer /dev/input (root o grupo `input`)."""
    if os.geteuid() == 0:
        return True
    if group_ids is None:
        group_ids = os.getgroups()
    if input_gid is None:
        import grp

        try:
            input_gid = grp.getgrnam("input").gr_gid
        except KeyError:
            return False
    return input_gid in set(group_ids)


INPUT_GROUP_CMD = "sudo usermod -aG input $USER"
INPUT_GROUP_HINT = (
    f"Añade tu usuario al grupo input: {INPUT_GROUP_CMD} y re-loguea. "
    "Ojo: el grupo input permite leer TODO el teclado (equivale a un keylogger); "
    "limita con hold_devices = [\"nombre del teclado\"]."
)


def _hold_ready(cfg) -> tuple[bool, str]:
    """(listo, motivo) para push-to-talk: evdev + permiso + teclado legible."""
    from .hotkey_hold import parse_chord

    chord = parse_chord(cfg.hold_key)
    if chord is None:
        return False, f"hold_key inválido: {cfg.hold_key!r}"
    try:
        import evdev  # noqa: F401
        from evdev import ecodes
    except ImportError:
        return False, "falta python-evdev (extra [hold])"
    if not hasattr(ecodes, chord.key):
        return False, f"tecla no soportada: {chord.key}"
    if not _input_group_ok():
        return False, "usuario fuera del grupo input"
    device = _hold_device_hint()
    if device.startswith(("sin permiso", "falta", "ningún")):
        return False, device
    return True, device


def _list_keyboards() -> list[tuple[str, str]]:
    """[(nombre, path)] de teclados legibles (EV_KEY + KEY_F). Requiere evdev.

    Lanza ImportError sin `python-evdev` y PermissionError si hay devices pero
    ninguno se puede abrir (falta el grupo `input`).
    """
    import glob

    import evdev
    from evdev import ecodes

    boards: list[tuple[str, str]] = []
    denied = False
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            dev = evdev.InputDevice(path, readonly=True)
        except PermissionError:
            denied = True
            continue
        except Exception:
            continue
        try:
            if ecodes.KEY_F in dev.capabilities().get(ecodes.EV_KEY, []):
                boards.append((dev.name or "?", path))
        finally:
            dev.close()
    if not boards and denied:
        raise PermissionError("sin permiso para /dev/input/event*")
    return boards


def cmd_keyboards(args):
    """Lista teclados y si coinciden con `hold_devices` (push-to-talk)."""
    from .hotkey_hold import device_matches

    cfg = _config_from_args(args)
    try:
        boards = _list_keyboards()
    except ImportError:
        print("Falta python-evdev: .venv/bin/pip install 'local-speech-to-text[hold]'")
        sys.exit(1)
    except PermissionError:
        print(INPUT_GROUP_HINT)
        sys.exit(1)
    if not boards:
        print("No se encontró ningún teclado legible en /dev/input/event*.")
        sys.exit(1)
    allow = cfg.hold_devices
    print(f"Teclados legibles ({len(boards)}) · allowlist: "
          f"{', '.join(allow) if allow else 'vacía (se escuchan todos)'}")
    for name, path in boards:
        mark = "✅" if device_matches(name, allow) else "  "
        print(f"  {mark} {name}  [{path}]")
    print("\nCopia el nombre (o un trozo) en hold_devices dentro de config.toml.")


def _hold_device_hint() -> str:
    """Primer teclado legible, o el motivo por el que no se puede abrir."""
    try:
        import glob

        import evdev
        from evdev import ecodes

        for path in sorted(glob.glob("/dev/input/event*")):
            try:
                dev = evdev.InputDevice(path, readonly=True)
            except PermissionError:
                return "sin permiso para /dev/input/event*"
            except Exception:
                continue
            try:
                caps = dev.capabilities().get(ecodes.EV_KEY, [])
                if ecodes.KEY_F in caps:
                    return f"{dev.name} ({path})"
            finally:
                dev.close()
        return "ningún teclado detectado"
    except ImportError:
        return "falta python-evdev"


def cmd_setup(args):
    """Puesta en marcha total: deps -> modelo -> atajos -> servicio -> doctor -> chuleta."""

    try:  # salida en orden aunque se redirija
        import sys as _sys

        _sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    cfg = _config_from_args(args)
    print("=" * 62)
    print("  local-stt setup — puesta en marcha asistida")
    print("=" * 62)

    # 1) deps de sistema
    print("\n[1/5] Dependencias de sistema")
    had_missing = _check_system_deps()
    if not had_missing:
        print("   ✅ todo presente")

    # 2) modelo pre-descargado
    print("\n[2/5] Modelo")
    try:
        from faster_whisper.utils import download_model

        download_model(cfg.model)
        print(f"   ✅ {cfg.model} listo")
    except Exception as e:
        print(f"   ⚠️  no se pudo descargar ahora ({e}); se bajará al primer dictado")

    # 3) atajos de teclado
    print("\n[3/5] Atajos (Win+F dictar, Win+Shift+F historial)")
    hotkey = _hotkey_script()
    if hotkey is not None:
        env = {**os.environ, "LOCAL_STT_DESKTOP": "auto"}
        if cfg.push_to_talk:
            # El listener evdev gestiona Win+F (press y release); si el
            # compositor también lo lanzara, el dictado se pararía solo.
            # Solo se desregistra si hold puede funcionar de verdad: si no,
            # el usuario se quedaría sin ningún atajo.
            ready, why = _hold_ready(cfg)
            if ready:
                env["LOCAL_STT_SKIP_TOGGLE"] = "1"
            else:
                print(f"   ⚠️  push_to_talk activo pero no disponible ({why})")
                print("      mantengo Win+F en modo toggle hasta que lo resuelvas")
                if "python-evdev" in why:
                    print("      instala: .venv/bin/pip install 'local-speech-to-text[hold]'")
                elif "input" in why:
                    print(f"      {INPUT_GROUP_CMD} y re-loguea")
        r = subprocess.run(["bash", str(hotkey)], env=env, timeout=60,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("   ✅ registrados" if r.returncode == 0 else
              "   ⚠️  no se pudieron registrar: configúralos en Ajustes → Atajos")
        print("      (KDE: cierra sesión y entra de nuevo para que apliquen)")
    else:
        print("   ⚠️  setup-hotkey.sh no encontrado: registra el atajo a mano")

    # 4) servicio systemd
    print("\n[4/5] Servicio systemd --user")
    unit_dst = _user_unit()
    unit_src = _repo_root() / "systemd" / SERVICE
    if not _service_installed() and unit_src.exists():
        unit_dst.parent.mkdir(parents=True, exist_ok=True)
        unit_dst.write_text(unit_src.read_text().replace("%h", str(Path.home())))
    if _service_installed():
        subprocess.run(["systemctl", "--user", "daemon-reload"], timeout=15)
        subprocess.run(["systemctl", "--user", "enable", "--now", "local-stt"], timeout=30)
        for _ in range(60):
            if cfg.socket_path.exists():
                break
            time.sleep(0.5)
        print("   ✅ daemon activo" if cfg.socket_path.exists() else "   ⚠️  arrancando lento: revisa 'local-stt doctor'")
        if cfg.socket_path.exists():
            # Aplica push-to-talk/OSD/idioma sin reiniciar (no recarga el modelo).
            resp = send_command("reload", cfg.socket_path)
            if resp.startswith("ok"):
                print(f"   ✅ config aplicada: {resp}")
            else:
                print(f"   ⚠️  no se pudo aplicar en caliente: {resp}")
    else:
        print("   ⚠️  sin unit systemd; corre 'local-stt daemon' manualmente")

    # 5) doctor + chuleta
    print("\n[5/5] Diagnóstico")
    doc = subprocess.run([sys.executable, "-m", "local_speech_to_text.cli", "doctor"],
                         timeout=120, capture_output=True, text=True,
                         env={**os.environ, "PYTHONUNBUFFERED": "1"})
    print("\n" + doc.stdout.strip())
    print("\n" + "=" * 62)
    if doc.returncode == 0:
        print("  🟢 TODO LISTO. Chuleta:")
    else:
        print("  Chuleta (arriba tienes lo que falta por resolver):")
    print("=" * 62)
    print(_cheatsheet())


def _cheatsheet() -> str:
    return """
  DICTAR          Win+F ... habla ... Win+F   → copia y pega (Ctrl+V)
  HISTORIAL       Win+Shift+F  → elige un dictado anterior (wofi)
  TRADUCIR        local-stt translate (alterna: dicta español → pega inglés)
  CONFIG          local-stt config   → menú interactivo
  RECARGAR        local-stt reload   → aplica cambios sin reiniciar
  MANOS LIBRES    di "hey jarvis" (wake_word = true en config.toml)
  DIAGNÓSTICO     local-stt doctor

  Dictado con puntuación hablada:
  "hola coma qué tal punto" → Hola, qué tal.
  "nueva línea" · "punto y aparte" · "abrir/cerrar paréntesis" · "arroba"
"""


def _strip_gnome_bindings(existing: str) -> str:
    """Quita nuestras entradas de la lista gsettings de atajos GNOME."""
    import re

    paths = re.findall(r"'([^']+)'", existing)
    kept = [p for p in paths if "local-stt" not in p]
    if not kept:
        return "@as []"
    return "[" + ", ".join(f"'{p}'" for p in kept) + "]"


def cmd_update(args):
    """Auto-actualiza: git pull -> pip install -e . -> tests -> restart daemon."""
    if is_packaged_install():
        print("Instalación empaquetada (pacman/AUR): actualiza con 'sudo pacman -Syu' o 'yay -Syu'.")
        return
    repo = _repo_root()
    def git(*a):
        return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, timeout=120)

    print(f"→ git pull en {repo}")
    pull = git("pull", "--ff-only")
    if pull.returncode != 0:
        print(f"❌ No se pudo actualizar (¿cambios locales?):\n{pull.stderr.strip()}")
        sys.exit(1)
    print(pull.stdout.strip() or "   ya estabas al día")

    print("→ pip install -e . (dependencias)")
    # ojo: el extra [wakeword] re-resolvería tflite-runtime, sin wheels para
    # py3.14; las deps ya instaladas en el venv sobreviven al reinstalar el base.
    pip = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-e", "."],
                         cwd=repo, timeout=600)
    if pip.returncode != 0:
        print("❌ pip falló; el daemon NO se reinicia (sigue con la versión anterior)")
        sys.exit(1)

    print("→ tests")
    tests = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q"], cwd=repo, timeout=300)
    if tests.returncode != 0:
        print("❌ tests fallaron tras la actualización: NO reinicio el daemon. Revisa el código nuevo.")
        sys.exit(1)

    if subprocess.run(["systemctl", "--user", "is-active", "--quiet", "local-stt"]).returncode == 0:
        subprocess.run(["systemctl", "--user", "restart", "local-stt"], timeout=60)
        print("→ daemon reiniciado con el código nuevo")
    print("✅ Actualizado. Verifica con: local-stt doctor")


def _importable(module: str) -> bool:
    try:
        __import__(module)
        return True
    except ImportError:
        return False


def is_packaged_install(bin_path: str | Path | None = None) -> bool:
    """True si el binario local-stt lo instaló el sistema (pacman/AUR: bajo /usr).

    Inyecta `bin_path` para tests; por defecto resuelve `local-stt` del PATH.
    """
    exe = str(bin_path) if bin_path is not None else shutil.which("local-stt")
    return exe is not None and Path(exe).resolve().is_relative_to("/usr")


def _purge_paths(packaged: bool) -> list[Path]:
    """Directorios que --purge borra. El venv del repo solo si NO es instalación empaquetada:
    con pacman/AUR (binario bajo /usr) el venv lo gestiona el paquete, no nosotros."""
    dirs = [
        Path.home() / ".config" / "local-stt",
        Path.home() / ".local" / "share" / "local-stt",
        Path.home() / ".local" / "state" / "local-stt",
    ]
    if not packaged:
        dirs.append(Path(__file__).resolve().parents[2] / ".venv")
    return dirs


def cmd_uninstall(args):
    """Desinstala: servicio, atajos (KDE/GNOME) y opcionalmente datos (--purge).

    Instalación empaquetada (pacman/AUR, binario bajo /usr): no se toca el venv
    del sistema; se sugiere quitar binario y venv con `sudo pacman -R local-stt`.
    """
    if not args.yes:
        print("Esto detiene el daemon y borra el servicio y los atajos. Usa --yes para confirmar.")
        sys.exit(1)
    packaged = is_packaged_install()

    print("→ deteniendo servicio")
    subprocess.run(["systemctl", "--user", "disable", "--now", "local-stt"], capture_output=True, timeout=30)
    unit = Path.home() / ".config" / "systemd" / "user" / "local-stt.service"
    if unit.exists():
        unit.unlink()
        subprocess.run(["systemctl", "--user", "daemon-reload"], timeout=15)

    print("→ quitando atajos")
    if shutil.which("kwriteconfig6"):
        subprocess.run(["kwriteconfig6", "--file", "khotkeysrc", "--group", "Data", "--key", "DataCount", "0"],
                       timeout=15)
    if shutil.which("gsettings"):
        existing = subprocess.run(
            ["gsettings", "get", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings"],
            capture_output=True, text=True, timeout=15).stdout.strip()
        subprocess.run(["gsettings", "set", "org.gnome.settings-daemon.plugins.media-keys",
                        "custom-keybindings", _strip_gnome_bindings(existing)], timeout=15)
    for p in ("/tmp/local-stt.sock", "/tmp/local-stt.pid"):
        Path(p).unlink(missing_ok=True)

    if args.purge:
        print("→ borrando datos y venv (--purge)" if not packaged else "→ borrando datos (--purge)")
        for d in _purge_paths(packaged):
            if d.exists():
                shutil.rmtree(d)
    if packaged:
        print("ℹ️  instalación empaquetada (binario bajo /usr): quítala con: sudo pacman -R local-stt")
    print("✅ Desinstalado." + ("" if args.purge else " Usa --purge además para borrar config/historial/.venv."))


def cmd_bench(args):
    """Compara modelos en tu GPU con un clip real (archivo o grabación)."""

    from .bench import bench_model, render_table

    cfg = _config_from_args(args)
    if args.file:
        import soundfile as sf

        audio, sr = sf.read(args.file, dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
    else:
        print(f"Grabando {args.seconds}s de tu micro para el benchmark... habla ahora")
        rec = AudioRecorder(sample_rate=cfg.sample_rate, mic=cfg.mic)
        rec.start()
        time.sleep(args.seconds)
        audio = rec.stop().samples
        sr = cfg.sample_rate
    if audio.size < cfg.sample_rate:
        print("❌ Clip demasiado corto (mínimo 1s).")
        sys.exit(1)

    models = args.models or ["small", "medium", "large-v3-turbo"]
    print(f"\nBenchmark sobre {audio.size / sr:.1f}s de audio ({cfg.device}, {cfg.compute_type}).")
    print("AVISO: los modelos no cacheados se descargan (~0.5-3GB cada uno).\n")
    rows = []
    for m in models:
        print(f"→ {m}...")
        try:
            rows.append(bench_model(m, audio, sr, cfg.device, cfg.compute_type, cfg.language))
        except Exception as e:
            print(f"   ⚠️ {m} falló: {e}")
    if not rows:
        print("❌ Ningún modelo completó el benchmark.")
        sys.exit(1)
    print("\n" + render_table(rows, current=cfg.model))


def cmd_stats(args):
    """Estadísticas de uso: dictados, palabras, tiempo y histograma."""
    from .stats import compute_stats, load_entries, render_stats

    cfg = _config_from_args(args)
    entries = load_entries(cfg.history_path)
    print(render_stats(compute_stats(entries, days=args.days)))


def cmd_config(args):
    """TUI interactivo para ~/.config/local-stt/config.toml (sin TTY: solo muestra)."""
    from .config_tui import run_tui

    cfg = _config_from_args(args)
    sys.exit(run_tui(cfg.config_path))


def cmd_doctor(args):
    """Diagnóstico: GPU, daemon, modelo, atajo, clipboard, micro."""
    from .clipboard import notify  # noqa: F401

    cfg = _config_from_args(args)
    print(f"== local-stt doctor | v{_version()} | modelo={cfg.model} device={cfg.device} ==")
    failures = 0

    # 1. Driver/GPU
    try:
        smi = subprocess.run(["nvidia-smi"], capture_output=True, timeout=10)
        smi_rc, smi_err = smi.returncode, smi.stderr.decode()[:200]
    except FileNotFoundError:
        smi_rc, smi_err = 1, "nvidia-smi no instalado"
    except Exception as e:
        smi_rc, smi_err = 1, str(e)
    nvr = Path("/proc/driver/nvidia/version")
    mismatch = nvr.exists() and smi_rc != 0
    failures += not _check(
        smi_rc == 0, "GPU driver",
        "nvidia-smi OK",
        smi_err + (" → kernel vs userspace DISTINTA: reinicia el equipo" if mismatch else "Reinstala nvidia-utils"),
    )

    # 2. CUDA en ctranslate2 + cuBLAS 12
    try:
        import ctranslate2

        n = ctranslate2.get_cuda_device_count()
        failures += not _check(n > 0, "CUDA (ctranslate2)", f"{n} dispositivo CUDA", "No hay CUDA: irá a CPU (lento)")
    except Exception as e:
        failures += not _check(False, "CUDA (ctranslate2)", "", f"error importando: {e}")
    from .cuda_libs import PACKAGED_CUBLAS_DIR, nvidia_pip_dir

    nv = nvidia_pip_dir()
    pip_lib = nv / "cublas" / "lib" / "libcublas.so.12"
    pkg_lib = PACKAGED_CUBLAS_DIR / "libcublas.so.12"
    failures += not _check(
        pip_lib.exists() or pkg_lib.exists(),
        "cuBLAS 12",
        str(pip_lib if pip_lib.exists() else pkg_lib),
        "Falta cuBLAS 12: instala nvidia-cublas-cu12 (venv) o el paquete local-stt (AUR)",
    )

    # 3. Daemon
    failures += not _check(cfg.socket_path.exists(), "Daemon", "corriendo",
                           "No corre. Se auto-arranca al usar el atajo, o: systemctl --user start local-stt", warn=True)

    # 4. Modelo descargado
    try:
        from huggingface_hub import constants as hf
        from faster_whisper.utils import _MODELS

        repo = _MODELS.get(cfg.model, cfg.model)
        cached = Path(hf.HF_HUB_CACHE) / ("models--" + repo.replace("/", "--"))
    except Exception:
        cached = None
    failures += not _check(
        cached is not None and cached.exists(), "Modelo",
        f"cacheado en {cached}",
        "No cacheado (primer uso tardará). Ejecuta: local-stt download", warn=True,
    )

    # 5. Clipboard / paste
    import shutil

    for tool, pkg, purpose in (
        ("wl-copy", "wl-clipboard", "copiar (Wayland)"),
        ("wtype", "wtype", "auto-pegar (Wayland)"),
        ("notify-send", "libnotify", "notificaciones"),
    ):
        failures += not _check(shutil.which(tool) is not None, tool, purpose,
                               f"Falta. Instala: sudo pacman -S {pkg}", warn=tool != "wl-copy")

    picker = _pick_tool()
    failures += not _check(picker is not None, "Selector (wofi/rofi)", picker or "",
                           "Falta para `local-stt pick` (Win+Shift+F): sudo pacman -S wofi", warn=True)

    # 5d. Detección de ventana activa (vocabulario contextual)
    from .active_window import get_active_window_name

    window = get_active_window_name()
    failures += not _check(window is not None, "Ventana activa", f"'{window[:60]}'" if window else "",
                           "Sin kdotool/xdotool el vocabulario contextual usará el default. "
                           "Exacto en KDE: yay -S kdotool", warn=True)

    # 5b. Vocabulario y correcciones
    from .vocab import load_corrections, load_vocabulary

    n_vocab = len([t for t in load_vocabulary(cfg.vocabulary_file).split(", ") if t])
    n_corr = len(load_corrections(cfg.corrections_file))
    _check(True, "Vocabulario", f"{n_vocab} términos en {cfg.vocabulary_file}",
           "")  # siempre OK: es opcional
    _check(True, "Correcciones", f"{n_corr} reglas en {cfg.corrections_file}", "")

    # 5c. Wake word (opcional)
    try:
        import openwakeword  # noqa: F401
        import onnxruntime  # noqa: F401

        _check(True, "Wake word", f"deps OK (modelo {cfg.wake_word_model})" +
               (", ACTIVO" if cfg.wake_word else ", apagado (wake_word = true para activar)"), "")
    except ImportError:
        _check(False, "Wake word", "", "Opcional. Instala: .venv/bin/pip install 'local-speech-to-text[wakeword]'", warn=True)

    # 5d. Push-to-talk (opcional: mantener la tecla para dictar)
    if not cfg.push_to_talk:
        _check(True, "Push-to-talk", "desactivado (modo toggle)", "")
    else:
        from .hotkey_hold import parse_chord

        chord = parse_chord(cfg.hold_key)
        failures += not _check(chord is not None, "Hold chord", cfg.hold_key,
                               "hold_key inválido: usa p. ej. 'super+f'")
        ok_group = _input_group_ok()
        failures += not _check(ok_group, "Grupo input",
                               "usuario en grupo input" if ok_group else "usuario FUERA del grupo input",
                               INPUT_GROUP_HINT, warn=True)
        device = _hold_device_hint()
        readable = not device.startswith(("sin permiso", "falta", "ningún"))
        failures += not _check(readable, "Teclado evdev", device,
                               "Sin lectura de /dev/input no hay hold", warn=True)
        if readable and cfg.hold_devices:
            from .hotkey_hold import device_matches

            try:
                boards = [name for name, _ in _list_keyboards()]
            except Exception:
                boards = []
            matched = [n for n in boards if device_matches(n, cfg.hold_devices)]
            failures += not _check(
                bool(matched), "Allowlist",
                f"{len(matched)}/{len(boards)} teclados coinciden",
                f"Ninguno coincide con {cfg.hold_devices}; revisa: local-stt keyboards",
            )
        if not cfg.hold_devices:
            _check(True, "Allowlist", "vacía: escucha todos los teclados",
                   "Considera hold_devices = [\"tu teclado\"] (ver README)")
        if cfg.socket_path.exists():
            status = send_command("status", cfg.socket_path)
            hold = status.split("hold=")[-1].split()[0] if "hold=" in status else "?"
            failures += not _check(hold == "running", "Hold listener", hold,
                                   "Reinicia el daemon: systemctl --user restart local-stt", warn=True)

    # 5e. OSD (informativo: Tk siempre funciona, GTK es la mejora)
    from .osd_backend import describe, gtk_layer_available, select_backend

    osd_backend, osd_reason = select_backend(cfg.osd_backend)
    osd_line = describe(osd_backend, osd_reason)
    if cfg.osd_backend.lower() == "gtk" and not gtk_layer_available():
        failures += not _check(False, "OSD", osd_line,
                               "osd_backend=gtk forzado pero GTK/layer-shell no importa: usa auto", warn=True)
    else:
        _check(True, "OSD", osd_line, "")

    # 6. Atajo
    if cfg.push_to_talk:
        _check(True, "Atajo Win+F", f"gestionado por push-to-talk ({cfg.hold_key})", "")
    else:
        hotkey = (Path.home() / ".config" / "khotkeysrc")
        configured = hotkey.exists() and "Local STT" in hotkey.read_text()
        failures += not _check(configured, "Atajo Win+F", "configurado en khotkeysrc",
                               "Ejecuta: local-stt setup", warn=True)

    # 7. Micrófono
    try:
        devs = AudioRecorder.list_devices()
        has_input = any(d["max_input_channels"] > 0 for d in devs)
        _check(has_input, "Micrófono", "dispositivo de entrada detectado",
               "No se detectó micro de entrada (revisa pavucontrol)", warn=False)
        if cfg.mic:
            r = AudioRecorder(mic=cfg.mic)
            idx = r.resolve_mic()
            failures += not _check(idx is not None, f"Mic '{cfg.mic}'",
                                   f"índice {idx}" if idx is not None else "",
                                   "No matchea ningún dispositivo de entrada; se usará el default del sistema", warn=True)
        else:
            _check(True, "Mic", "config.mic vacío: se usa el default del sistema "
                   "(elige uno fijo con local-stt config)", "")
    except Exception as e:
        failures += not _check(False, "Micrófono", "", f"error: {e}")

    print("\n" + ("🟢 Todo listo para dictar." if failures == 0 else f"🔴 {failures} problema(s) por resolver."))
    sys.exit(0 if failures == 0 else 1)


def cmd_transcribe_file(args):
    """Transcribe un wav/mp3 sin daemon, útil para probar el modelo."""
    import soundfile as sf
    import numpy as np

    from .transcriber import Transcriber

    cfg = _config_from_args(args)
    data, sr = sf.read(args.file, dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    if sr != 16000:
        try:
            import librosa

            data = librosa.resample(data, orig_sr=sr, target_sr=16000)
            sr = 16000
        except ImportError:
            print(f"[warn] Audio a {sr}Hz, se enviará tal cual (instala librosa para resample perfecto)")

    tr = Transcriber(model=cfg.model, device=cfg.device, compute_type=cfg.compute_type, language=cfg.language)
    text = tr.transcribe(data.astype(np.float32), sr)
    print("\n--- Transcripción ---")
    print(text)
    if args.copy:
        from .clipboard import copy_to_clipboard

        copy_to_clipboard(text)
        print("\n(copiado al portapapeles)")


def _version() -> str:
    """Versión instalada (metadatos del paquete); fallback si no hay metadata."""
    try:
        from importlib.metadata import version

        return version("local-speech-to-text")
    except Exception:
        return "desconocida"


def main(argv: list[str] | None = None):
    try:  # salida en orden en pipes/redirecciones (CLI interactivo)
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass
    p = argparse.ArgumentParser(prog="local-stt", description="Dictado local RTX 5070: Win+F -> copiar -> Ctrl+V")
    p.add_argument("--version", "-V", action="version", version=f"local-stt {_version()}")
    p.add_argument("--model", default=None, help="Modelo faster-whisper (default: large-v3-turbo)")
    p.add_argument("--lang", default="es", help="Idioma: es, en, auto (default: es)")
    p.add_argument("--device", default=None, choices=["cuda", "cpu"], help="cuda o cpu")
    p.add_argument("--compute", default=None, help="float16, int8_float16, float32, int8")

    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("daemon", help="Inicia el daemon (mantiene modelo en VRAM)")
    d.set_defaults(func=cmd_daemon)

    t = sub.add_parser("toggle", help="Alterna grabación; auto-arranca el daemon si hace falta")
    t.set_defaults(func=cmd_toggle)

    s = sub.add_parser("status", help="Estado del daemon")
    s.set_defaults(func=cmd_status)

    osd = sub.add_parser("osd", help="Estado del OSD (backend, dependencias y margen)")
    osd.add_argument("--check", action="store_true",
                     help="exit 1 si el backend configurado no puede arrancar")
    osd.add_argument("--preview", action="store_true",
                     help="Muestra el OSD unos segundos sin dictar")
    osd.add_argument("--seconds", type=float, default=6.0,
                     help="Duración de la vista previa (default 6s)")
    osd.set_defaults(func=cmd_osd)

    q = sub.add_parser("stop", help="Detiene el daemon")
    q.set_defaults(func=cmd_stop)

    r = sub.add_parser("reload", help="Recarga config en caliente (modelo/idioma/vocab)")
    r.set_defaults(func=cmd_reload)

    tr = sub.add_parser("translate", help="Alterna traducción: dicta en tu idioma, sale en inglés")
    tr.set_defaults(func=cmd_translate)

    dev = sub.add_parser("devices", help="Lista micrófonos")
    dev.set_defaults(func=cmd_devices)

    kb = sub.add_parser("keyboards", help="Lista teclados para push-to-talk (hold_devices)")
    kb.set_defaults(func=cmd_keyboards)

    h = sub.add_parser("history", help="Últimas transcripciones")
    h.add_argument("--count", "-n", type=int, default=10, help="Cuántas mostrar (default 10)")
    h.add_argument("--copy", type=int, nargs="?", const=1, metavar="N",
                   help="Copiar al portapapeles la N-ésima (1=última). Solo: copia la última")
    h.set_defaults(func=cmd_history)

    pk = sub.add_parser("pick", help="Selector visual (wofi/rofi) del historial → copia y pega")
    pk.add_argument("--count", "-n", type=int, default=20, help="Cuántas mostrar (default 20)")
    pk.add_argument("--no-paste", dest="paste", action="store_false",
                    help="Solo copiar, no enviar Ctrl+V")
    pk.set_defaults(func=cmd_pick, paste=True)

    dl = sub.add_parser("download", help="Pre-descarga el modelo (primer uso instantáneo)")
    dl.set_defaults(func=cmd_download)

    doc = sub.add_parser("doctor", help="Diagnóstico completo: GPU, daemon, atajo, micro...")
    doc.set_defaults(func=cmd_doctor)

    v = sub.add_parser("vocab", help="Vocabulario para Whisper (nombres/términos propios)")
    v.add_argument("action", nargs="?", default="list", choices=["list", "add", "remove"])
    v.add_argument("terms", nargs="*", help="Términos (add/remove)")
    v.set_defaults(func=cmd_vocab)

    c = sub.add_parser("correct", help="Añade corrección: local-stt correct 'mal' 'bien'")
    c.add_argument("wrong", help="Texto que sale mal")
    c.add_argument("right", help="Texto correcto")
    c.set_defaults(func=cmd_correct)

    cf = sub.add_parser("config", help="TUI: editar config.toml interactivamente")
    cf.set_defaults(func=cmd_config)

    st = sub.add_parser("setup", help="Puesta en marcha total: deps, modelo, atajos, servicio, doctor")
    st.set_defaults(func=cmd_setup)

    up = sub.add_parser("update", help="git pull + pip install + tests + restart del daemon")
    up.set_defaults(func=cmd_update)

    un = sub.add_parser(
        "uninstall",
        help="Quita servicio y atajos (--purge borra también datos). "
        "Instalado con pacman/AUR: sudo pacman -R local-stt",
    )
    un.add_argument("--yes", action="store_true", help="Confirmar sin prompt")
    un.add_argument("--purge", action="store_true", help="Borrar config, historial y .venv")
    un.set_defaults(func=cmd_uninstall)

    stat = sub.add_parser("stats", help="Uso: dictados, palabras, tiempo, histograma")
    stat.add_argument("--days", type=int, default=14, help="Días del histograma (default 14)")
    stat.set_defaults(func=cmd_stats)

    bn = sub.add_parser("bench", help="Benchmark de modelos en tu GPU (clip tuyo)")
    bn.add_argument("file", nargs="?", help="Audio wav/mp3; si falta, graba del micro")
    bn.add_argument("--seconds", type=float, default=6, help="Segundos a grabar si no hay archivo")
    bn.add_argument("--models", nargs="+", help="Modelos a comparar (default: small medium large-v3-turbo)")
    bn.set_defaults(func=cmd_bench)

    f = sub.add_parser("transcribe", help="Transcribe un archivo de audio")
    f.add_argument("file", help="Ruta a wav/mp3/flac")
    f.add_argument("--copy", action="store_true", help="Copiar al portapapeles")
    f.set_defaults(func=cmd_transcribe_file)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
