from pathlib import Path

from local_speech_to_text.wakeword import WakeWordMonitor, resolve_model_path


def test_resolve_model_path_nombre_a_archivo():
    p = resolve_model_path("hey_jarvis")
    assert p.endswith(".onnx")
    assert Path(p).exists()


def test_resolve_model_path_ruta_absoluta_se_respeta(tmp_path):
    custom = tmp_path / "custom.onnx"
    custom.write_bytes(b"x")
    assert resolve_model_path(str(custom)) == str(custom)


def test_resolve_model_path_nombre_desconocido_no_explota():
    # devuelve el nombre tal cual si no encuentra el modelo (fallará al cargar)
    assert resolve_model_path("modelo_inexistente") == "modelo_inexistente"


def test_monitor_sin_arrancar_no_falla():
    m = WakeWordMonitor(on_wake=lambda: None, model_path="no.onnx")
    m.pause()
    m.resume()
    m.stop()
    assert m._thread is None
