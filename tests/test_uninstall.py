
import shutil
from pathlib import Path

import pytest

from local_speech_to_text.cli import _strip_gnome_bindings


def test_strip_gnome_bindings_quita_solo_las_nuestras():
    existing = "['/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom-local-stt/', '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom-local-stt-pick/', '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom-screen/']"
    out = _strip_gnome_bindings(existing)
    assert "custom-local-stt" not in out
    assert "custom-screen" in out


def test_strip_gnome_bindings_vacia_resultante():
    assert _strip_gnome_bindings("['/org/gnome/.../custom-local-stt/']") == "@as []"


def test_strip_gnome_bindings_lista_vacia_de_origen():
    assert _strip_gnome_bindings("@as []") == "@as []"


def test_strip_gnome_bindings_mantiene_otras_dos():
    existing = "['/a/custom-local-stt/', '/b/otro/', '/c/tercero/']"
    out = _strip_gnome_bindings(existing)
    assert out.count("'") == 4  # dos entradas


def test_uninstall_sin_yes_no_hace_nada(monkeypatch, capsys):
    """Sin --yes solo avisa y sale 1, sin tocar el sistema."""
    from local_speech_to_text import cli

    calls = []
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: calls.append(a) or type("R", (), {"returncode": 0})())

    class Args:
        yes = False
        purge = False

    with pytest.raises(SystemExit) as e:
        cli.cmd_uninstall(Args())
    assert e.value.code == 1
    assert calls == []  # no ejecutó nada
    assert "--yes" in capsys.readouterr().out


# ---- detección de instalación empaquetada (pacman/AUR) ----


def test_is_packaged_install_detecta_binario_en_usr_bin():
    from local_speech_to_text.cli import is_packaged_install

    assert is_packaged_install("/usr/bin/local-stt") is True


def test_is_packaged_install_rechaza_venv_del_repo():
    from local_speech_to_text.cli import is_packaged_install

    venv_bin = "/home/x/dev/local_speech_to_text/.venv/bin/local-stt"
    assert is_packaged_install(venv_bin) is False


def test_is_packaged_install_sin_binario(monkeypatch):
    from local_speech_to_text import cli

    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    assert cli.is_packaged_install() is False


def test_is_packaged_install_con_which_en_usr_bin(monkeypatch):
    from local_speech_to_text import cli

    def fake_which(name):
        return "/usr/bin/local-stt" if name == "local-stt" else None

    monkeypatch.setattr(cli.shutil, "which", fake_which)
    assert cli.is_packaged_install() is True


# ---- uninstall consciente de pacman/AUR ----


class _YesPurgeArgs:
    yes = True
    purge = True


def _mock_uninstall_env(monkeypatch, tmp_path, packaged):
    """Aísla cmd_uninstall: home/repo falsos, subprocess simulado y borrados registrados.

    Retorna (calls, removed, unlinked, venv): llamadas a subprocess.run, rutas
    pasadas a shutil.rmtree, rutas pasadas a Path.unlink y el venv del repo falso.
    """
    from local_speech_to_text import cli

    calls = []
    monkeypatch.setattr(
        cli.subprocess, "run",
        lambda *a, **k: calls.append(a) or type("R", (), {"returncode": 0, "stdout": ""})(),
    )
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    repo = tmp_path / "repo"
    monkeypatch.setattr(cli, "__file__", str(repo / "src" / "local_speech_to_text" / "cli.py"))
    monkeypatch.setattr(cli, "is_packaged_install", lambda *a, **k: packaged)

    def fake_which(name):
        if packaged and name == "local-stt":
            return "/usr/bin/local-stt"
        return f"/usr/bin/{name}"  # herramientas del sistema: subprocess ya está simulado

    monkeypatch.setattr(cli.shutil, "which", fake_which)

    removed, unlinked = [], []
    real_rmtree = shutil.rmtree
    monkeypatch.setattr(
        shutil, "rmtree",
        lambda p, *a, **k: removed.append(str(p)) or real_rmtree(p, *a, **k),
    )
    monkeypatch.setattr(Path, "unlink", lambda self, missing_ok=False: unlinked.append(str(self)))
    return calls, removed, unlinked, repo / ".venv"


def test_uninstall_empaquetado_no_toca_venv_y_sugiere_pacman(monkeypatch, capsys, tmp_path):
    """Binario en /usr/bin (pacman/AUR): purge borra config pero NUNCA el venv.

    El venv del repo no existe (instalación del sistema); aún así se verifica
    que ni se intenta borrar, se mantiene el borrado de servicio/atajos y se
    sugiere quitar los archivos del sistema con pacman.
    """
    from local_speech_to_text import cli

    calls, removed, unlinked, venv = _mock_uninstall_env(monkeypatch, tmp_path, packaged=True)
    cfg = tmp_path / ".config" / "local-stt"
    cfg.mkdir(parents=True)
    (cfg / "config.toml").write_text("model = 'small'\n")

    cli.cmd_uninstall(_YesPurgeArgs)

    out = capsys.readouterr().out
    assert "sudo pacman -R local-stt" in out
    assert "y venv" not in out  # no promete borrar un venv que no es nuestro
    assert any(c[0] and c[0][0] == "systemctl" for c in calls)  # sigue quitando el servicio
    assert "quitando atajos" in out  # sigue quitando los atajos
    assert not cfg.exists()  # la config del usuario sí se borra con --purge
    assert str(venv) not in removed  # ni se intenta borrar el venv


def test_uninstall_venv_local_con_purge_borra_venv_sin_pacman(monkeypatch, capsys, tmp_path):
    """Invariante: instalación de repo (venv existente) NO cambia el comportamiento."""
    from local_speech_to_text import cli

    calls, removed, unlinked, venv = _mock_uninstall_env(monkeypatch, tmp_path, packaged=False)
    venv.mkdir(parents=True)
    (venv / "bin").mkdir()

    cli.cmd_uninstall(_YesPurgeArgs)

    out = capsys.readouterr().out
    assert not venv.exists()  # con --purge el venv del repo se borra como antes
    assert str(venv) in removed
    assert "y venv (--purge)" in out
    assert "pacman" not in out  # no hay nada que quitar con pacman


def test_uninstall_empaquetado_jamas_borra_bajo_usr(monkeypatch, tmp_path):
    """Security: con el binario en /usr/bin/local-stt nada bajo /usr se toca."""
    from local_speech_to_text import cli

    calls, removed, unlinked, venv = _mock_uninstall_env(monkeypatch, tmp_path, packaged=True)
    venv.mkdir(parents=True)  # aunque exista: pertenece al paquete, no se toca

    cli.cmd_uninstall(_YesPurgeArgs)

    for p in removed + unlinked:
        assert not p.startswith("/usr"), f"se intentó borrar bajo /usr: {p}"
    assert str(venv) not in removed

