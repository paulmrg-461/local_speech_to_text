from local_speech_to_text.bench import bench_model, render_table


ROWS = [
    {"model": "small", "load_s": 1.2, "trans_s": 0.15, "rtf": 0.02, "chars": 40, "text": "hola mundo"},
    {"model": "large-v3-turbo", "load_s": 9.0, "trans_s": 0.30, "rtf": 0.05, "chars": 42, "text": "hola mundo mejor"},
    {"model": "medium", "load_s": 4.0, "trans_s": 0.80, "rtf": 0.13, "chars": 41, "text": "hola mundo bueno"},
]


def test_render_ordenado_por_velocidad():
    out = render_table(ROWS, current="medium")
    lines = [ln for ln in out.splitlines() if ln.startswith(("small", "large", "medium"))]
    assert lines[0].startswith("small")        # más rápido primero
    assert lines[-1].startswith("medium")      # más lento al final


def test_render_marca_modelo_actual():
    out = render_table(ROWS, current="large-v3-turbo")
    assert "← actual" in out


def test_render_sugerencia():
    out = render_table(ROWS, current="medium")
    assert "Más rápido: small" in out
    assert "RTF" in out


def test_render_trunca_preview():
    long_row = dict(ROWS[0], text="x" * 100)
    out = render_table([long_row], current="small")
    assert "…" in out


def test_bench_model_e2e_cuda():
    """Smoke test real: tiny en CUDA con 1s de ruido (rápido y ya cacheado)."""
    import numpy as np

    row = bench_model("tiny", np.zeros((16000,), dtype=np.float32), 16000,
                      device="cuda", compute="float16", language="es")
    assert row["model"] == "tiny"
    assert row["load_s"] >= 0
    assert row["trans_s"] >= 0
    assert row["text"] == ""
