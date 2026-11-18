"""El paquete AUR debe seguir siendo coherente con lo que espera el código.

Si el PKGBUILD instala algo en una ruta distinta de la que lee `cli.py` o
`cuda_libs.py`, la instalación empaquetada se rompe en silencio (daemon sin
unit, cuBLAS sin precargar, atajos sin script). Estos tests fijan ese contrato.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from local_speech_to_text import cli
from local_speech_to_text.cuda_libs import _PRELOAD, PACKAGED_CUBLAS_DIR

ROOT = Path(__file__).resolve().parents[1]
AUR = ROOT / "packaging" / "aur"
PKGBUILD = AUR / "PKGBUILD"
SRCINFO = AUR / ".SRCINFO"


def _pkgbuild() -> str:
    return PKGBUILD.read_text()


def _array(text: str, name: str) -> list[str]:
    """Entradas de un array bash `name=( ... )`, sin comentarios."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith(f"{name}=("):
            continue
        inline = line.split("(", 1)[1]
        if inline.rstrip().endswith(")"):
            body = [inline.rsplit(")", 1)[0]]
        else:
            body = [inline]
            for following in lines[index + 1:]:
                if following.strip() == ")":
                    break
                body.append(following)
        return [
            value
            for value in (item.split("#")[0].strip().strip("'\"") for item in body)
            if value
        ]
    raise AssertionError(f"{name} no encontrado en PKGBUILD")


def _scalar(text: str, name: str) -> str:
    match = re.search(rf"^{name}=(.+)$", text, re.M)
    assert match, f"{name} no encontrado"
    return match.group(1).strip().strip("'\"")


def test_pkgbuild_declara_el_paquete():
    text = _pkgbuild()
    assert _scalar(text, "pkgname") == "local-stt"
    assert "x86_64" in text
    assert _array(text, "license") == ["MIT"]
    assert (ROOT / "LICENSE").exists()


def test_pkgver_sigue_a_pyproject():
    """Un release en pyproject sin subir pkgver empaquetaría la versión vieja."""
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert _scalar(_pkgbuild(), "pkgver") == version
    assert f"pkgver = {version}" in SRCINFO.read_text()


def test_srcinfo_refleja_depends_del_pkgbuild():
    text = _pkgbuild()
    srcinfo = SRCINFO.read_text()
    for dep in _array(text, "depends"):
        assert f"depends = {dep}" in srcinfo
    for opt in _array(text, "optdepends"):
        assert f"optdepends = {opt}" in srcinfo
    assert _array(text, "depends") == re.findall(r"^\tdepends = (\S+)$", srcinfo, re.M)


def test_cublas_empaquetado_va_donde_lo_lee_cuda_libs():
    text = _pkgbuild()
    assert str(PACKAGED_CUBLAS_DIR) in text
    for rel in _PRELOAD:
        assert Path(rel).name in text


def test_unit_empaquetado_usa_el_binario_del_sistema():
    unit = (AUR / "local-stt.service").read_text()
    assert "ExecStart=/usr/bin/local-stt daemon" in unit
    assert "%h/Documents" not in unit
    assert "WantedBy=default.target" in unit


def test_pkgbuild_instala_unit_y_atajos_donde_los_busca_cli():
    text = _pkgbuild()
    assert f"{cli.SYSTEM_UNIT_DIR}/{cli.SERVICE}" in text
    assert f"{cli.SHARE_DIR}/setup-hotkey.sh" in text


def test_hotkey_script_prefiere_el_repo_y_cae_al_paquete(tmp_path):
    repo = tmp_path / "repo"
    share = tmp_path / "share"
    assert cli._hotkey_script(repo_root=repo, share_dir=share) is None

    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "setup-hotkey.sh").write_text("#!/bin/sh\n")
    assert cli._hotkey_script(repo_root=repo, share_dir=share) == repo / "scripts" / "setup-hotkey.sh"

    packaged = share / "setup-hotkey.sh"
    share.mkdir()
    packaged.write_text("#!/bin/sh\n")
    assert cli._hotkey_script(repo_root=tmp_path / "vacio", share_dir=share) == packaged


def test_service_installed_detecta_unit_del_paquete(tmp_path):
    user = tmp_path / "user" / "local-stt.service"
    system = tmp_path / "system" / "local-stt.service"
    assert cli._service_installed(user_unit=user, system_unit=system) is False

    system.parent.mkdir()
    system.write_text("[Unit]\n")
    assert cli._service_installed(user_unit=user, system_unit=system) is True


def test_update_en_instalacion_empaquetada_no_toca_git(monkeypatch, capsys):
    monkeypatch.setattr(cli, "is_packaged_install", lambda: True)
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *a, **k: pytest.fail("no debe ejecutar git/pip en un paquete pacman"),
    )

    cli.cmd_update(None)

    out = capsys.readouterr().out
    assert "pacman" in out
