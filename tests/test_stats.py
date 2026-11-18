import json
from datetime import date, timedelta

from local_speech_to_text.stats import compute_stats, load_entries, render_stats


def _entry(text="hola mundo", days_ago=0, duration=None):
    ts = (date.today() - timedelta(days=days_ago)).isoformat() + "T12:00:00"
    return {"ts": ts, "text": text, "duration": duration}


def test_stats_vacias():
    assert compute_stats([]) == {"total": 0}
    assert "Sin datos" in render_stats({"total": 0})


def test_stats_totales_y_medias():
    entries = [_entry("uno dos tres cuatro", days_ago=1, duration=10.0),
               _entry("cinco seis", days_ago=1, duration=5.0),
               _entry("siete", days_ago=2)]
    stats = compute_stats(entries)
    assert stats["total"] == 3
    assert stats["words"] == 7
    assert stats["avg_words"] > 2
    assert stats["dictated_secs"] == 15.0


def test_stats_histograma_ventana():
    entries = [_entry(days_ago=0), _entry(days_ago=0), _entry(days_ago=5)]
    stats = compute_stats(entries, days=7)
    assert len(stats["days"]) == 7
    today = date.today().isoformat()
    assert dict(stats["days"])[today] == 2


def test_render_stats_con_datos():
    stats = compute_stats([_entry("hola", days_ago=0, duration=3.0)])
    out = render_stats(stats)
    assert "Dictados:" in out
    assert "0.1 min" in out
    assert "█" in out or "▏" in out
    assert date.today().isoformat() in out


def test_render_stats_sin_duracion_mensaje_claro():
    stats = compute_stats([_entry("hola")])
    assert "sin duración" in render_stats(stats)


def test_load_entries_ignora_lineas_rotas(tmp_path):
    f = tmp_path / "history.jsonl"
    f.write_text(json.dumps(_entry("ok")) + "\nLÍNEA ROTA\n" + json.dumps(_entry("ok2")) + "\n\n")
    assert len(load_entries(f)) == 2
    assert load_entries(tmp_path / "no-existe") == []
