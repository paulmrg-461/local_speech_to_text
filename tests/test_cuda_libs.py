import ctypes

from local_speech_to_text.cuda_libs import nvidia_pip_dir, preload_cuda_libs


def test_sin_directorio_nvidia_no_falla(tmp_path, capsys):
    loaded = preload_cuda_libs(site_packages=tmp_path)
    assert loaded == []
    assert "se omite preload" in capsys.readouterr().out


def test_nvidia_pip_dir_apunta_bajo_site_packages(tmp_path):
    assert nvidia_pip_dir(tmp_path) == tmp_path / "nvidia"


def test_preload_carga_libs_reales_si_existen():
    """Smoke test: si el paquete nvidia-cublas-cu12 está instalado, debe cargarlo."""
    loaded = preload_cuda_libs()
    for name in loaded:
        assert name in ("libcublas.so.12", "libcublasLt.so.12")
    # si cargó algo, la lib queda registrada con RTLD_GLOBAL y dlopen la resuelve
    if loaded:
        ctypes.CDLL("libcublas.so.12")
