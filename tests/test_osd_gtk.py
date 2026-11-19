"""`osd_gtk.py` debe importarse sin GTK y decidir --check con código limpio."""

from __future__ import annotations

import pytest

from local_speech_to_text import osd_gtk


def test_import_sin_gi():
    """El módulo no importa gi a nivel superior (venv/CI sin PyGObject)."""
    assert osd_gtk.TICK_MS == 100
    assert osd_gtk.DEFAULT_SOCK.endswith("local-stt.sock")


def test_parse_args_defaults():
    assert osd_gtk.parse_args([]) == ("/tmp/local-stt.sock", 80, None, "")


def test_parse_args_socket_y_margen():
    sock, margin, preview, monitor = osd_gtk.parse_args(["/tmp/x.sock", "--margin", "120"])
    assert sock == "/tmp/x.sock"
    assert margin == 120
    assert preview is None
    assert monitor == ""


def test_parse_args_preview():
    assert osd_gtk.parse_args(["--preview"]) == ("/tmp/local-stt.sock", 80, 6.0, "")
    sock, _, preview, _ = osd_gtk.parse_args(["--preview", "--seconds", "2.5"])
    assert sock == "/tmp/local-stt.sock"
    assert preview == 2.5


def test_parse_args_monitor():
    assert osd_gtk.parse_args(["--monitor", "HDMI-1"]) == ("/tmp/local-stt.sock", 80, None, "HDMI-1")


def test_match_monitor_por_indice_y_nombre():
    names = ["eDP-1", "HDMI-A-1", "DP-2"]
    assert osd_gtk.match_monitor("1", names) == 1
    assert osd_gtk.match_monitor("hdmi", names) == 1
    assert osd_gtk.match_monitor("DP-2", names) == 2
    assert osd_gtk.match_monitor("VGA", names) is None
    assert osd_gtk.match_monitor("", names) is None


def test_parse_args_ignora_check():
    assert osd_gtk.parse_args(["--check"])[0] == "/tmp/local-stt.sock"


def test_parse_args_margen_debe_ser_entero():
    with pytest.raises(ValueError):
        osd_gtk.parse_args(["--margin", "arriba"])


def test_check_es_booleano():
    assert isinstance(osd_gtk.check(), bool)


def test_main_check_sale_0_o_3():
    with pytest.raises(SystemExit) as exc:
        osd_gtk.main(["--check"])
    assert exc.value.code in (0, 3)
    assert exc.value.code == (0 if osd_gtk.check() else 3)
