from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import Config
from .daemon import Daemon, send_command
from .recorder import AudioRecorder


def cmd_daemon(args):
    cfg = Config(
        model=args.model,
        language=None if args.lang == "auto" else args.lang,
        device=args.device,
        compute_type=args.compute,
    )
    d = Daemon(cfg)
    d.start()


def cmd_toggle(args):
    resp = send_command("toggle")
    print(resp)
    if "no corre" in resp:
        sys.exit(1)


def cmd_status(args):
    resp = send_command("status")
    print(resp)


def cmd_stop(args):
    resp = send_command("quit")
    print(resp)


def cmd_devices(args):
    print(AudioRecorder.list_devices())


def cmd_transcribe_file(args):
    """Transcribe un wav/mp3 sin daemon, útil para probar el modelo."""
    import soundfile as sf
    import numpy as np

    from .transcriber import Transcriber

    cfg = Config(model=args.model, device=args.device, compute_type=args.compute, language=None if args.lang == "auto" else args.lang)
    # cargar audio
    data, sr = sf.read(args.file, dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    # resample simple si hace falta (faster-whisper ya resamplea, pero lo hacemos manual si librosa disponible)
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
    p.add_argument("--model", default="large-v3-turbo", help="Modelo faster-whisper (default: large-v3-turbo)")
    p.add_argument("--lang", default="es", help="Idioma: es, en, auto (default: es)")
    p.add_argument("--device", default="cuda", choices=["cuda", "cpu"], help="cuda o cpu")
    p.add_argument("--compute", default="float16", help="float16, int8_float16, float32, int8")

    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("daemon", help="Inicia el daemon (mantiene modelo en VRAM)")
    d.set_defaults(func=cmd_daemon)

    t = sub.add_parser("toggle", help="Alterna grabación (llamado por el atajo Win+F)")
    t.set_defaults(func=cmd_toggle)

    s = sub.add_parser("status", help="Estado del daemon")
    s.set_defaults(func=cmd_status)

    q = sub.add_parser("stop", help="Detiene el daemon")
    q.set_defaults(func=cmd_stop)

    dev = sub.add_parser("devices", help="Lista micrófonos")
    dev.set_defaults(func=cmd_devices)

    f = sub.add_parser("transcribe", help="Transcribe un archivo de audio")
    f.add_argument("file", help="Ruta a wav/mp3/flac")
    f.add_argument("--copy", action="store_true", help="Copiar al portapapeles")
    f.set_defaults(func=cmd_transcribe_file)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
