"""Benchmark de modelos sobre TU GPU con TU voz (local-stt bench).

Compara carga + transcripción del mismo clip entre modelos y sugiere el
más rápido. `bench` no carga modelos en paralelo: uno, mide, descarga.
"""

from __future__ import annotations

import time


def bench_model(model: str, audio, sample_rate: int, device: str, compute: str, language: str | None) -> dict:
    """Carga un modelo, transcribe el clip y devuelve métricas."""
    from .transcriber import Transcriber

    t0 = time.time()
    tr = Transcriber(model=model, device=device, compute_type=compute, language=language)
    load_s = time.time() - t0
    t0 = time.time()
    text = tr.transcribe(audio, sample_rate)
    trans_s = time.time() - t0
    del tr  # libera VRAM antes del siguiente modelo
    return {
        "model": model,
        "load_s": round(load_s, 1),
        "trans_s": round(trans_s, 2),
        "rtf": round(trans_s / max(0.01, len(audio) / sample_rate), 2),
        "chars": len(text),
        "text": text,
    }


def render_table(rows: list[dict], current: str) -> str:
    """Tabla comparativa ordenada por velocidad de transcripción."""
    lines = [f"{'modelo':<20} {'carga':>6} {'transc':>7} {'RTF':>6}  texto", "-" * 70]
    for r in sorted(rows, key=lambda r: r["trans_s"]):
        mark = " ← actual" if r["model"] == current else ""
        preview = r["text"][:34] + ("…" if len(r["text"]) > 34 else "")
        lines.append(f"{r['model']:<20} {r['load_s']:>5}s {r['trans_s']:>6}s {r['rtf']:>6}  {preview}{mark}")
    fastest = min(rows, key=lambda r: r["trans_s"])
    lines.append(f"\n⚡ Más rápido: {fastest['model']} — cambia con: local-stt config "
                 f"(o model = \"{fastest['model']}\" + local-stt reload)")
    lines.append("RTF < 1 = más rápido que tiempo real.")
    return "\n".join(lines)
