"""Estadísticas de uso desde el historial JSONL (local-stt stats)."""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from pathlib import Path


def compute_stats(entries: list[dict], days: int = 14) -> dict:
    """Métricas agregadas de las entradas del historial."""
    if not entries:
        return {"total": 0}
    words = sum(len(e.get("text", "").split()) for e in entries)
    chars = sum(len(e.get("text", "")) for e in entries)
    durations = [e["duration"] for e in entries if e.get("duration")]
    by_day: Counter[str] = Counter()
    for e in entries:
        try:
            by_day[e["ts"][:10]] += 1
        except (KeyError, TypeError):
            continue
    today = date.today()
    window = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    return {
        "total": len(entries),
        "words": words,
        "chars": chars,
        "avg_words": words / len(entries),
        "dictated_secs": sum(durations) if durations else None,
        "days": [(d, by_day.get(d, 0)) for d in window],
        "best_day": by_day.most_common(1)[0],
    }


def render_stats(stats: dict) -> str:
    """Salida humana con mini histograma de los últimos 14 días."""
    if stats.get("total", 0) == 0:
        return "Sin datos todavía: dicta algo primero (Win+F)."
    secs = stats.get("dictated_secs")
    lines = [
        f"Dictados:   {stats['total']}",
        f"Palabras:   {stats['words']}  ({stats['avg_words']:.0f} por dictado de media)",
        f"Caracteres: {stats['chars']}",
    ]
    if secs:
        lines.append(f"Tiempo dictando: {secs / 60:.1f} min")
    else:
        lines.append("Tiempo dictando: (entradas antiguas sin duración)")
    if stats.get("best_day"):
        day, count = stats["best_day"]
        lines.append(f"Mejor día:  {day} ({count} dictados)")
    max_count = max(c for _, c in stats["days"]) or 1
    lines.append("\nÚltimos 14 días:")
    for day, count in stats["days"]:
        bar = "█" * int(count / max_count * 24)
        lines.append(f"  {day}  {'▏' if not count else bar} {count}")
    return "\n".join(lines)


def load_entries(path: Path) -> list[dict]:
    import json

    if not path.exists():
        return []
    out = []
    for ln in path.read_text().splitlines():
        ln = ln.strip()
        if ln:
            try:
                out.append(json.loads(ln))
            except ValueError:
                continue
    return out
