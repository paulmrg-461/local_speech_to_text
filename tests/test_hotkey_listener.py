"""Listener evdev: filtrado, allowlist y cableado con el daemon (T4-T6).

No requiere `python-evdev`: la fuente de eventos se inyecta.
"""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

import pytest

from local_speech_to_text import hotkey_hold
from local_speech_to_text.config import Config
from local_speech_to_text.daemon import Daemon
from local_speech_to_text.hotkey_hold import (
    ARMED,
    TAP_OPEN,
    HoldChord,
    HotkeyListener,
    KeyEvent,
    device_matches,
    parse_chord,
)


class FakeSource:
    def __init__(self, reason: str | None = None) -> None:
        self.reason = reason
        self.opened = False
        self.closed = False
        self.events: list[KeyEvent] = []

    def open(self) -> str | None:
        self.opened = True
        return self.reason

    def poll(self, timeout: float) -> list[KeyEvent]:
        if self.events:
            return [self.events.pop(0)]
        time.sleep(min(timeout, 0.01))
        return []

    def close(self) -> None:
        self.closed = True


def _listener(min_ms=0, source=None):
    calls: list[str] = []
    chord = parse_chord("super+f")
    listener = HotkeyListener(
        chord,
        min_ms=min_ms,
        on_start=lambda: calls.append("start"),
        on_stop=lambda: calls.append("stop"),
        source=source or FakeSource(),
    )
    return listener, calls


# --- allowlist -----------------------------------------------------------

@pytest.mark.parametrize(
    "name,allowlist,expected",
    [
        ("AT Translated Set 2 keyboard", (), True),
        ("AT Translated Set 2 keyboard", ("AT Translated",), True),
        ("AT Translated Set 2 keyboard", ("at translated",), True),
        ("AT Translated Set 2 keyboard", ("Logitech",), False),
        ("Logitech USB Keyboard", ("AT Translated", "Logitech"), True),
        ("", ("Logitech",), False),
    ],
)
def test_device_matches(name, allowlist, expected):
    assert device_matches(name, allowlist) is expected


# --- filtrado de eventos -------------------------------------------------

def test_hold_completo():
    listener, calls = _listener(min_ms=0)
    listener.handle_event(KeyEvent("KEY_LEFTMETA", 1))
    listener.handle_event(KeyEvent("KEY_F", 1))
    assert calls == ["start"]
    assert listener.machine.state == ARMED
    listener.handle_event(KeyEvent("KEY_F", 0))
    assert calls == ["start", "stop"]


def test_soltar_meta_antes_que_f_termina_el_hold():
    listener, calls = _listener(min_ms=0)
    listener.handle_event(KeyEvent("KEY_LEFTMETA", 1))
    listener.handle_event(KeyEvent("KEY_F", 1))
    listener.handle_event(KeyEvent("KEY_LEFTMETA", 0))
    assert calls == ["start", "stop"]


def test_tap_no_para_y_el_segundo_tap_si():
    listener, calls = _listener(min_ms=1000)
    listener.handle_event(KeyEvent("KEY_LEFTMETA", 1))
    listener.handle_event(KeyEvent("KEY_F", 1))
    listener.handle_event(KeyEvent("KEY_F", 0))
    assert calls == ["start"]
    assert listener.machine.state == TAP_OPEN
    listener.handle_event(KeyEvent("KEY_F", 1))
    listener.handle_event(KeyEvent("KEY_F", 0))
    assert calls == ["start", "stop"]


def test_auto_repeat_no_duplica_comandos():
    listener, calls = _listener(min_ms=0)
    listener.handle_event(KeyEvent("KEY_LEFTMETA", 1))
    listener.handle_event(KeyEvent("KEY_F", 1))
    for _ in range(5):
        listener.handle_event(KeyEvent("KEY_F", 2))
    listener.handle_event(KeyEvent("KEY_F", 0))
    assert calls == ["start", "stop"]


def test_teclas_ajenas_se_ignoran():
    listener, calls = _listener(min_ms=0)
    listener.handle_event(KeyEvent("KEY_LEFTMETA", 1))
    listener.handle_event(KeyEvent("KEY_A", 1))
    listener.handle_event(KeyEvent("KEY_A", 0))
    assert calls == []
    assert listener.machine.state == "idle"


def test_f_sin_meta_no_dispara():
    listener, calls = _listener(min_ms=0)
    listener.handle_event(KeyEvent("KEY_F", 1))
    listener.handle_event(KeyEvent("KEY_F", 0))
    assert calls == []


# --- arranque y estado ---------------------------------------------------

def test_start_sin_evdev_falla_con_motivo():
    source = FakeSource(reason="no-evdev")
    listener, _ = _listener(source=source)
    assert listener.start() is False
    assert listener.status == "no-evdev"
    assert source.opened


def test_start_sin_permiso_falla_sin_tumbar_nada():
    listener, calls = _listener(source=FakeSource(reason="no-permission"))
    assert listener.start() is False
    assert listener.status == "no-permission"
    listener.stop()
    assert calls == []


def test_start_ok_y_stop():
    source = FakeSource()
    listener, _ = _listener(source=source)
    assert listener.start() is True
    assert listener.status == "running"
    listener.stop()
    assert listener.status == "stopped"
    assert source.closed


def test_evdev_rechaza_chord_con_tecla_inexistente():
    pytest.importorskip("evdev", reason="requiere el extra [hold]")
    from local_speech_to_text.hotkey_hold import EvdevSource

    source = EvdevSource({"KEY_XYZ"}, chord_key="KEY_XYZ")
    assert source.open() == "bad-chord"


# --- cableado con el daemon ----------------------------------------------

class _FakeRecorder:
    sample_rate = 16000

    def __init__(self) -> None:
        self.is_recording = False


def _daemon_stub(monkeypatch, reason=None):
    import threading

    fake = FakeSource(reason=reason)
    monkeypatch.setattr(hotkey_hold, "EvdevSource", lambda *a, **k: fake)

    d = Daemon.__new__(Daemon)
    d.recorder = _FakeRecorder()
    d._lock = threading.Lock()
    d._recording_origin = None
    d.hold_listener = None
    d.hold_status = "off"
    d.wake_monitor = None
    d.config = replace(
        Config.load(config_file=Path("/no/existe.toml")),
        push_to_talk=True,
        hold_devices=[],
        hold_min_ms=0,
    )
    d.calls = []

    def _start():
        d.calls.append("start")
        d.recorder.is_recording = True

    def _stop():
        d.calls.append("stop")
        d.recorder.is_recording = False
        d._recording_origin = None

    d._start_recording = _start
    d._stop_and_transcribe = _stop
    return d, fake


def test_daemon_arranca_listener_y_dicta(monkeypatch):
    d, _ = _daemon_stub(monkeypatch)
    d._start_hold_listener()
    assert d.hold_status == "running"
    assert d.hold_listener is not None

    machine = d.hold_listener.machine
    machine.press()
    assert d.calls == ["start"]
    assert d._recording_origin == "hold"
    machine.release()
    assert d.calls == ["start", "stop"]
    d._stop_hold_listener()
    assert d.hold_listener is None


def test_daemon_desactivado_no_arranca_listener(monkeypatch):
    d, fake = _daemon_stub(monkeypatch)
    object.__setattr__(d.config, "push_to_talk", False)
    d._start_hold_listener()
    assert d.hold_status == "off"
    assert d.hold_listener is None
    assert fake.opened is False


def test_daemon_sin_permiso_sigue_en_toggle(monkeypatch):
    d, fake = _daemon_stub(monkeypatch, reason="no-permission")
    d._start_hold_listener()
    assert d.hold_status == "no-permission"
    assert d.hold_listener is None
    # el toggle normal sigue operativo
    d.toggle()
    assert d.calls == ["start"]


def test_daemon_chord_invalido_no_arranca(monkeypatch):
    d, _ = _daemon_stub(monkeypatch)
    object.__setattr__(d.config, "hold_key", "hola+f")
    d._start_hold_listener()
    assert d.hold_status == "bad-chord"
    assert d.hold_listener is None


def test_grabacion_externa_no_la_para_el_release(monkeypatch):
    d, _ = _daemon_stub(monkeypatch)
    d._start_hold_listener()
    d.toggle()  # grabación iniciada por toggle
    machine = d.hold_listener.machine
    machine.press()
    machine.release()
    assert d.calls == ["start"]  # el release del hold no la paró
    assert d._recording_origin == "toggle"


def test_chord_parseado_una_sola_vez():
    assert isinstance(parse_chord("super+f"), HoldChord)


def test_reload_reinicia_listener_al_cambiar_hold(monkeypatch):
    from local_speech_to_text import daemon as daemon_mod

    d, _ = _daemon_stub(monkeypatch)
    d._start_hold_listener()
    d._osd_choice = ("gtk", "cacheado")
    old_listener = d.hold_listener
    assert old_listener is not None

    new_cfg = replace(d.config, hold_min_ms=350)
    monkeypatch.setattr(daemon_mod.Config, "load", classmethod(lambda cls, **kw: new_cfg))

    out = d.reload_config()

    assert out.startswith("ok recargado")
    assert d.hold_listener is not None
    assert d.hold_listener is not old_listener  # reiniciado con la config nueva
    assert d.hold_listener.machine.min_ms == 350
    assert d._osd_choice is None  # el backend se re-sondea al próximo dictado
