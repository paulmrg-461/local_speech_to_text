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

# Instalación empaquetada (pacman/AUR): el PKGBUILD copia libcublas.so.12 y
# libcublasLt.so.12 directamente en este directorio, sin subdirectorios.
PACKAGED_CUBLAS_DIR = Path("/usr/lib/local-stt/cublas")


def nvidia_pip_dir(site_packages: Path | None = None) -> Path:
    """Directorio `nvidia/` de los paquetes pip dentro de site-packages."""
    base = site_packages or Path(sysconfig.get_paths()["purelib"])
    return base / "nvidia"


def _candidatos(nv_dir: Path, packaged: Path) -> list[Path]:
    """Rutas candidatas: primero el paquete pip, luego la instalación empaquetada."""
    rutas = [nv_dir / rel for rel in _PRELOAD]
    rutas += [packaged / Path(rel).name for rel in _PRELOAD]
    return rutas


def _cargar_libs(rutas: list[Path]) -> list[str]:
    """dlopen (RTLD_GLOBAL) cada lib existente; ignora fallos individuales."""
    loaded: list[str] = []
    for lib in rutas:
        if not lib.exists():
            continue
        try:
            ctypes.CDLL(str(lib), mode=ctypes.RTLD_GLOBAL)
            loaded.append(lib.name)
        except OSError as e:
            print(f"[cuda] no se pudo precargar {lib.name}: {e}")
    return loaded


def preload_cuda_libs(
    site_packages: Path | None = None,
    packaged_dir: Path | None = None,
) -> list[str]:
    """Precarga libcublas 12 con RTLD_GLOBAL. Retorna las libs cargadas.

    Busca primero el paquete pip (site-packages/nvidia) y luego la instalación
    empaquetada por pacman/AUR (por defecto /usr/lib/local-stt/cublas).
    Es idempotente y no falla si ninguna existe (CPU u otros SO).
    Debe llamarse ANTES de crear el WhisperModel en CUDA.
    """
    nv_dir = nvidia_pip_dir(site_packages)
    packaged = packaged_dir or PACKAGED_CUBLAS_DIR
    if not nv_dir.is_dir() and not packaged.is_dir():
        print(f"[cuda] {nv_dir} no existe: se omite preload (¿CPU o sin nvidia-cublas-cu12?)")
        return []
    loaded = _cargar_libs(_candidatos(nv_dir, packaged))
    if loaded:
        print(f"[cuda] precargadas: {', '.join(loaded)}")
    return loaded
