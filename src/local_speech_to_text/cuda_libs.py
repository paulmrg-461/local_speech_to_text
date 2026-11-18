from __future__ import annotations

import ctypes
import sysconfig
from pathlib import Path

# Libs CUDA 12 que ctranslate2 (compilado contra CUDA 12) hace dlopen en runtime.
# Arch/EndeavourOS instala CUDA 13 (libcublas.so.13), por eso falla con
# "Library libcublas.so.12 is not found". El paquete pip nvidia-cublas-cu12
# trae la versión 12 y la precargamos con RTLD_GLOBAL antes de usar la GPU:
# una vez cargada por soname, el dlopen posterior de ctranslate2 la resuelve.
_PRELOAD = (
    "cublas/lib/libcublas.so.12",
    "cublas/lib/libcublasLt.so.12",
)


def nvidia_pip_dir(site_packages: Path | None = None) -> Path:
    """Directorio `nvidia/` de los paquetes pip dentro de site-packages."""
    base = site_packages or Path(sysconfig.get_paths()["purelib"])
    return base / "nvidia"


def preload_cuda_libs(site_packages: Path | None = None) -> list[str]:
    """Precarga libcublas 12 con RTLD_GLOBAL. Retorna las libs cargadas.

    Es idempotente y no falla si no existe el paquete (CPU u otros SO).
    Debe llamarse ANTES de crear el WhisperModel en CUDA.
    """
    nv_dir = nvidia_pip_dir(site_packages)
    if not nv_dir.is_dir():
        print(f"[cuda] {nv_dir} no existe: se omite preload (¿CPU o sin nvidia-cublas-cu12?)")
        return []
    loaded: list[str] = []
    for rel in _PRELOAD:
        lib = nv_dir / rel
        if not lib.exists():
            continue
        try:
            ctypes.CDLL(str(lib), mode=ctypes.RTLD_GLOBAL)
            loaded.append(lib.name)
        except OSError as e:
            print(f"[cuda] no se pudo precargar {lib.name}: {e}")
    if loaded:
        print(f"[cuda] precargadas: {', '.join(loaded)}")
    return loaded
