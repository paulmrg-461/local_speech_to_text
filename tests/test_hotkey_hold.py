"""Push-to-talk: parser de chord, config y máquina de estados (sin evdev)."""

from pathlib import Path

import pytest

from local_speech_to_text.config import Config
from local_speech_to_text.hotkey_hold import (
    ARMED,
    EXTERNAL,
    IDLE,
    TAP_OPEN,
    HoldChord,
    HoldStateMachine,
    parse_chord,
)


class Clock:
    """Reloj inyectable para no dormir en los tests."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, ms: float) -> None:
        self.now += ms / 1000


# --- parse_chord ---------------------------------------------------------

@pytest.mark.parametrize(
    "text,key,mods",
    [
        ("super+f", "KEY_F", {"meta"}),
        ("Win+F", "KEY_F", {"meta"}),
        ("meta + f", "KEY_F", {"meta"}),
        ("ctrl+alt+d", "KEY_D", {"ctrl", "alt"}),
        ("SHIFT+SPACE", "KEY_SPACE", {"shift"}),
        ("ctrl+shift+f12", "KEY_F12", {"ctrl", "shift"}),
    ],
)
def test_parse_chord_valido(text, key, mods):
    chord = parse_chord(text)
    assert chord is not None
    assert chord.key == key
    assert chord.mods == frozenset(mods)


@pytest.mark.parametrize("text", ["", "   ", "f", "super", "super+", "+f", "hola+f", "super+¿"])
def test_parse_chord_invalido(text):
    assert parse_chord(text) is None


def test_chord_matches_exige_tecla_y_modificadores():
    chord = parse_chord("super+f")
    assert chord.matches("KEY_F", frozenset({"meta"}))
    assert chord.matches("KEY_F", frozenset({"meta", "shift"}))  # extra no molesta
    assert not chord.matches("KEY_G", frozenset({"meta"}))
    assert not chord.matches("KEY_F", frozenset())


def test_chord_normaliza_texto():
    assert parse_chord("Win + F").text == "meta+f"


# --- config --------------------------------------------------------------

def _clean_env(monkeypatch):
    for var in ("LOCAL_STT_PUSH_TO_TALK", "LOCAL_STT_HOLD_KEY",
                "LOCAL_STT_HOLD_MIN_MS", "LOCAL_STT_HOLD_DEVICES"):
        monkeypatch.delenv(var, raising=False)


def test_config_defaults_hold(monkeypatch, tmp_path):
    _clean_env(monkeypatch)
    cfg = Config.load(config_file=tmp_path / "no.toml")
    assert cfg.push_to_talk is False
    assert cfg.hold_key == "super+f"
    assert cfg.hold_min_ms == 200
    assert cfg.hold_devices == []


def test_config_toml_hold(monkeypatch, tmp_path):
    _clean_env(monkeypatch)
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        'push_to_talk = true\nhold_key = "ctrl+alt+d"\nhold_min_ms = 350\n'
        'hold_devices = ["AT Translated", "Logitech"]\n'
    )
    cfg = Config.load(config_file=cfg_file)
    assert cfg.push_to_talk is True
    assert cfg.hold_key == "ctrl+alt+d"
    assert cfg.hold_min_ms == 350
    assert cfg.hold_devices == ["AT Translated", "Logitech"]


def test_config_env_hold(monkeypatch, tmp_path):
    _clean_env(monkeypatch)
    monkeypatch.setenv("LOCAL_STT_PUSH_TO_TALK", "1")
    monkeypatch.setenv("LOCAL_STT_HOLD_KEY", "win+d")
    monkeypatch.setenv("LOCAL_STT_HOLD_MIN_MS", "120")
    monkeypatch.setenv("LOCAL_STT_HOLD_DEVICES", "AT Translated, Logitech")
    cfg = Config.load(config_file=tmp_path / "no.toml")
    assert cfg.push_to_talk is True
    assert cfg.hold_key == "win+d"
    assert cfg.hold_min_ms == 120
    assert cfg.hold_devices == ["AT Translated", "Logitech"]


def test_config_hold_min_negativo_cae_al_default(monkeypatch, tmp_path):
    _clean_env(monkeypatch)
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("hold_min_ms = -5\n")
    assert Config.load(config_file=cfg_file).hold_min_ms == 200


def test_config_hold_devices_como_string_toml(monkeypatch, tmp_path):
    _clean_env(monkeypatch)
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('hold_devices = "AT Translated, Logitech"\n')
    assert Config.load(config_file=cfg_file).hold_devices == ["AT Translated", "Logitech"]


def test_config_hold_devices_normaliza_tipos_y_espacios(monkeypatch, tmp_path):
    _clean_env(monkeypatch)
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('hold_devices = [" AT Translated ", 3, ""]\n')
    assert Config.load(config_file=cfg_file).hold_devices == ["AT Translated", "3"]


def test_config_normaliza_hold_key_y_osd_backend(monkeypatch, tmp_path):
    """Un TOML con tipos raros no debe tumbar el daemon al arrancar."""
    _clean_env(monkeypatch)
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("hold_key = 5\nosd_backend = 5\n")
    cfg = Config.load(config_file=cfg_file)
    assert cfg.hold_key == "5"
    assert cfg.osd_backend == "auto"


def test_config_defaults_sin_fichero(monkeypatch):
    _clean_env(monkeypatch)
    cfg = Config.load(config_file=Path("/no/existe.toml"))
    assert cfg.push_to_talk is False


# --- máquina de estados --------------------------------------------------

def _machine(clock, min_ms=200):
    events = []
    chord = HoldChord(key="KEY_F", mods=frozenset({"meta"}), text="meta+f")
    m = HoldStateMachine(
        chord,
        min_ms=min_ms,
        on_start=lambda: events.append("start"),
        on_stop=lambda: events.append("stop"),
        clock=clock,
    )
    return m, events


def test_hold_largo_arranca_y_para():
    clock = Clock()
    m, events = _machine(clock)
    m.press()
    assert events == ["start"]
    assert m.state == ARMED
    clock.advance(300)
    m.release()
    assert events == ["start", "stop"]
    assert m.state == IDLE


def test_tap_arranca_y_deja_grabando():
    """Primer toque = primer toggle: no debe parar la grabación."""
    clock = Clock()
    m, events = _machine(clock)
    m.press()
    clock.advance(120)
    m.release()
    assert events == ["start"]
    assert m.state == TAP_OPEN


def test_segundo_tap_para():
    clock = Clock()
    m, events = _machine(clock)
    m.press()
    clock.advance(120)
    m.release()
    m.press()
    clock.advance(120)
    m.release()
    assert events == ["start", "stop"]
    assert m.state == IDLE


def test_release_sin_press_no_hace_nada():
    clock = Clock()
    m, events = _machine(clock)
    m.release()
    assert events == []
    assert m.state == IDLE


def test_grabacion_externa_no_la_para_el_hold():
    clock = Clock()
    m, events = _machine(clock)
    m.notify_recording_started("wake")
    assert m.state == EXTERNAL
    m.press()
    clock.advance(400)
    m.release()
    assert events == []


def test_release_tras_watchdog_no_para_nada():
    clock = Clock()
    m, events = _machine(clock)
    m.press()
    m.notify_recording_stopped()  # watchdog/max_record_seconds
    clock.advance(400)
    m.release()
    assert events == ["start"]


def test_min_ms_cero_todo_es_hold():
    clock = Clock()
    m, events = _machine(clock, min_ms=0)
    m.press()
    m.release()
    assert events == ["start", "stop"]


def test_min_ms_negativo_se_normaliza_a_cero():
    clock = Clock()
    m, events = _machine(clock, min_ms=-50)
    m.press()
    m.release()
    assert events == ["start", "stop"]


def test_press_repetido_no_reinicia_grabacion():
    clock = Clock()
    m, events = _machine(clock)
    m.press()
    m.press()
    m.press()
    assert events == ["start"]  # una sola grabación
