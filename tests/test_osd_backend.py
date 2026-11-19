"""OSD: lógica pura de backend y formato (sin GTK ni Tk)."""

from __future__ import annotations

import json
import socket
import threading

import pytest

from local_speech_to_text import osd_backend as ob


def test_bar_fraction():
    assert ob.bar_fraction(0.0) == 0.0
    assert ob.bar_fraction(0.075) == pytest.approx(0.5)
    assert ob.bar_fraction(0.15) == 1.0
    assert ob.bar_fraction(0.5) == 1.0  # tope
    assert ob.bar_fraction(-0.1) == 0.0
    assert ob.bar_fraction(0.1, full_scale=0) == 0.0


def test_format_status():
    assert ob.format_status({"elapsed": 12.4, "partial": "hola"}) == "[  12s]  hola"
    assert ob.format_status({"elapsed": 0, "partial": "a\nb"}) == "[   0s]  a b"
    long = "x" * 200
    out = ob.format_status({"elapsed": 1, "partial": long})
    assert out.endswith("x" * 90)
    assert len(out) == len("[   1s]  ") + 90


@pytest.mark.parametrize(
    "info,expected",
    [
        (None, True),
        ({}, True),
        ({"recording": False}, True),
        ({"recording": True}, False),
    ],
)
def test_should_exit(info, expected):
    assert ob.should_exit(info) is expected


def test_preview_info_contrato():
    info = ob.preview_info(0.0)
    assert info["recording"] is True
    assert info["elapsed"] == 0.0
    assert 0.0 <= info["rms"] <= 0.15
    assert "Vista previa" in info["partial"]
    assert ob.format_status(ob.preview_info(3.0)).startswith("[   3s]")
    assert ob.should_exit(info) is False


def test_tk_parse_argv():
    from local_speech_to_text.osd import parse_argv

    assert parse_argv([]) == ("/tmp/local-stt.sock", None)
    assert parse_argv(["/tmp/y.sock"]) == ("/tmp/y.sock", None)
    assert parse_argv(["/tmp/y.sock", "--preview", "--seconds", "1.5"]) == ("/tmp/y.sock", 1.5)


@pytest.mark.parametrize(
    "session,wayland,probe,forced,expected",
    [
        ("wayland", "wayland-1", True, "auto", "gtk"),
        ("wayland", "wayland-1", False, "auto", "tk"),
        ("wayland", "", True, "auto", "tk"),
        ("x11", ":0", True, "auto", "tk"),
        ("tty", None, True, "auto", "tk"),
        ("x11", None, True, "gtk", "gtk"),  # override
        ("wayland", "wayland-1", True, "tk", "tk"),
        ("wayland", "wayland-1", False, "AUTO", "tk"),
    ],
)
def test_choose_backend(session, wayland, probe, forced, expected):
    assert ob.choose_backend(session, wayland, probe, forced) == expected


def test_select_backend_auto_gtk():
    backend, reason = ob.select_backend(
        "auto", env={"XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": "wayland-1"}, probe=True
    )
    assert backend == "gtk"
    assert "layer-shell" in reason


def test_select_backend_fallback_motivos():
    backend, reason = ob.select_backend("auto", env={"XDG_SESSION_TYPE": "x11"}, probe=True)
    assert backend == "tk" and "sesión" in reason

    backend, reason = ob.select_backend(
        "auto", env={"XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": ""}, probe=True
    )
    assert backend == "tk" and "WAYLAND_DISPLAY" in reason

    backend, reason = ob.select_backend(
        "auto", env={"XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": "wayland-1"}, probe=False
    )
    assert backend == "tk" and "layer-shell" in reason


def test_select_backend_forzado_avisa_sin_wayland():
    backend, reason = ob.select_backend("gtk", env={"XDG_SESSION_TYPE": "x11"}, probe=True)
    assert backend == "gtk"
    assert "puede fallar" in reason


def test_gtk_layer_available_usa_el_rc_del_proceso():
    assert ob.gtk_layer_available(python="/bin/true") is True
    assert ob.gtk_layer_available(python="/bin/false") is False
    assert ob.gtk_layer_available(python="/no/existe/python") is False


def test_find_system_python_existe():
    py = ob.find_system_python()
    assert py is None or py.endswith("python3")


def test_describe():
    assert ob.describe("gtk", "wayland").startswith("gtk-layer")
    assert ob.describe("tk", "x11").startswith("tk ·")


def test_query_level_contra_socket(tmp_path):
    sock = tmp_path / "osd.sock"
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(sock))
    srv.listen(1)

    def serve():
        conn, _ = srv.accept()
        assert conn.recv(1024).decode().strip() == "level"
        conn.sendall((json.dumps({"recording": True, "elapsed": 1.5, "rms": 0.02}) + "\n").encode())
        conn.close()

    threading.Thread(target=serve, daemon=True).start()
    info = ob.query_level(str(sock))
    assert info["recording"] is True
    assert info["rms"] == 0.02
    srv.close()


def test_query_level_sin_socket(tmp_path):
    assert ob.query_level(str(tmp_path / "nada.sock"), timeout=0.1) is None
