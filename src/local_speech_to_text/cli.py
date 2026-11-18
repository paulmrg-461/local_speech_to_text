from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from .config import Config
from .daemon import Daemon, send_command
from .recorder import AudioRecorder

SERVICE = "local-stt.service"


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
        unit = Path.home() / ".config" / "systemd" / "user" / SERVICE
        if unit.exists():
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


def cmd_stop(args):
    resp = send_command("quit", _config_from_args(args).socket_path)
    print(resp)


def cmd_reload(args):
    """Recarga config (TOML/env) sin reiniciar el daemon. Cambia modelo/idioma al vuelo."""
    resp = send_command("reload", _config_from_args(args).socket_path)
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
            print(f"Vocabulario vacío. Añade con: local-stt vocab add 'DevPaul' 'FastAPI'")
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


def cmd_doctor(args):
    """Diagnóstico: GPU, daemon, modelo, atajo, clipboard, micro."""
    from .clipboard import notify  # noqa: F401

    cfg = _config_from_args(args)
    print(f"== local-stt doctor | modelo={cfg.model} device={cfg.device} ==")
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
    from .cuda_libs import nvidia_pip_dir

    nv = nvidia_pip_dir()
    failures += not _check((nv / "cublas" / "lib" / "libcublas.so.12").exists(), "cuBLAS 12 (pip)",
                           f"{nv}", f"Falta nvidia-cublas-cu12: .venv/bin/pip install nvidia-cublas-cu12")

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

    # 5b. Vocabulario y correcciones
    from .vocab import load_corrections, load_vocabulary

    n_vocab = len([t for t in load_vocabulary(cfg.vocabulary_file).split(", ") if t])
    n_corr = len(load_corrections(cfg.corrections_file))
    _check(True, "Vocabulario", f"{n_vocab} términos en {cfg.vocabulary_file}",
           "")  # siempre OK: es opcional
    _check(True, "Correcciones", f"{n_corr} reglas en {cfg.corrections_file}", "")

    # 6. Atajo
    hotkey = (Path.home() / ".config" / "khotkeysrc")
    configured = hotkey.exists() and "Local STT" in hotkey.read_text()
    failures += not _check(configured, "Atajo Win+F", "configurado en khotkeysrc",
                           "Ejecuta: ./scripts/setup-hotkey.sh", warn=True)

    # 7. Micrófono
    try:
        devs = AudioRecorder.list_devices()
        has_input = any(d["max_input_channels"] > 0 for d in devs)
        failures += not _check(has_input, "Micrófono", "dispositivo de entrada detectado",
                               "No se detectó micro de entrada (revisa pavucontrol)", warn=False)
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


def main():
    p = argparse.ArgumentParser(prog="local-stt", description="Dictado local RTX 5070: Win+F -> copiar -> Ctrl+V")
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

    q = sub.add_parser("stop", help="Detiene el daemon")
    q.set_defaults(func=cmd_stop)

    r = sub.add_parser("reload", help="Recarga config en caliente (modelo/idioma/vocab)")
    r.set_defaults(func=cmd_reload)

    dev = sub.add_parser("devices", help="Lista micrófonos")
    dev.set_defaults(func=cmd_devices)

    h = sub.add_parser("history", help="Últimas transcripciones")
    h.add_argument("--count", "-n", type=int, default=10, help="Cuántas mostrar (default 10)")
    h.add_argument("--copy", type=int, nargs="?", const=1, metavar="N",
                   help="Copiar al portapapeles la N-ésima (1=última). Solo: copia la última")
    h.set_defaults(func=cmd_history)

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

    f = sub.add_parser("transcribe", help="Transcribe un archivo de audio")
    f.add_argument("file", help="Ruta a wav/mp3/flac")
    f.add_argument("--copy", action="store_true", help="Copiar al portapapeles")
    f.set_defaults(func=cmd_transcribe_file)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
