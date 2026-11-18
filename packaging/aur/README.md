# packaging/aur

Paquete Arch para `local-stt`. Instala sin venv:

- Código en `/usr/lib/python3.x/site-packages/local_speech_to_text/`
- Binario en `/usr/bin/local-stt`
- Unit de usuario en `/usr/lib/systemd/user/local-stt.service`
- Atajos en `/usr/share/local-stt/setup-hotkey.sh`
- cuBLAS 12 en `/usr/lib/local-stt/cublas/` (Arch trae CUDA 13; ver `cuda_libs.py`)

## Uso

```bash
cd packaging/aur
makepkg -si                 # build + install
local-stt setup             # modelo, atajos, servicio
```

## Publicar una versión nueva

1. Etiqueta el repo: `git tag v0.1.0 && git push --tags`.
2. Actualiza `pkgver`/`pkgrel` en `PKGBUILD`.
3. `updpkgsums` (o fija el SHA256 del tarball a mano).
4. `makepkg --printsrcinfo > .SRCINFO`.
5. Sube `PKGBUILD`, `.SRCINFO`, `local-stt.install` al repo de AUR.

`sha256sums` del wheel de cuBLAS es fija y corresponde a la versión
`_cublas_ver` del PKGBUILD; si la subes, recalcula el hash.
