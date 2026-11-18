import ctypes
from pathlib import Path

from local_speech_to_text.cuda_libs import (
    PACKAGED_CUBLAS_DIR,
    nvidia_pip_dir,
    preload_cuda_libs,
)


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


def _crear_libs_empaquetadas(packaged: Path) -> None:
    """Crea ficheros dummy (no ELF) que simulan la instalación pacman/AUR."""
    packaged.mkdir(parents=True)
    for nombre in ("libcublas.so.12", "libcublasLt.so.12"):
        (packaged / nombre).write_text("dummy")


def _mock_cdll(monkeypatch, llamadas: list[str]) -> None:
    """Sustituye ctypes.CDLL para no depender de libs CUDA reales en CI."""

    def fake_cdll(ruta: str, mode: int = ctypes.RTLD_LOCAL) -> object:
        llamadas.append(ruta)
        return object()

    monkeypatch.setattr(ctypes, "CDLL", fake_cdll)


def test_directorio_empaquetado_por_defecto():
    """El PKGBUILD instala las libs en /usr/lib/local-stt/cublas."""
    assert PACKAGED_CUBLAS_DIR == Path("/usr/lib/local-stt/cublas")


def test_preload_carga_libs_empaquetadas(tmp_path, monkeypatch):
    """Instalación pacman/AUR: dummy libs en packaged_dir, CDLL mockeado."""
    packaged = tmp_path / "cublas"
    _crear_libs_empaquetadas(packaged)
    llamadas: list[str] = []
    _mock_cdll(monkeypatch, llamadas)
    loaded = preload_cuda_libs(site_packages=tmp_path / "site-packages", packaged_dir=packaged)
    assert loaded == ["libcublas.so.12", "libcublasLt.so.12"]
    assert llamadas == [
        str(packaged / "libcublas.so.12"),
        str(packaged / "libcublasLt.so.12"),
    ]


def test_preload_prefiere_dir_pip_sobre_empaquetado(tmp_path, monkeypatch):
    """Si ambas instalaciones existen, se intenta primero el paquete pip."""
    pip_lib = tmp_path / "site-packages" / "nvidia" / "cublas" / "lib"
    pip_lib.mkdir(parents=True)
    (pip_lib / "libcublas.so.12").write_text("dummy")
    packaged = tmp_path / "cublas"
    _crear_libs_empaquetadas(packaged)
    llamadas: list[str] = []
    _mock_cdll(monkeypatch, llamadas)
    loaded = preload_cuda_libs(site_packages=tmp_path / "site-packages", packaged_dir=packaged)
    assert llamadas[0] == str(pip_lib / "libcublas.so.12")
    assert set(loaded) == {"libcublas.so.12", "libcublasLt.so.12"}
