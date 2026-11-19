"""Daemon: elige Vosk u openWakeWord según `wake_word_engine`."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from local_speech_to_text import wakeword
from local_speech_to_text.config import Config
from local_speech_to_text.daemon import Daemon


def _daemon(monkeypatch, **cfg_kw):
    d = Daemon.__new__(Daemon)
    d.wake_monitor = None
    d.config = replace(Config.load(config_file=Path("/no/existe.toml")), **cfg_kw)
    d._on_wake = lambda: None
    monkeypatch.setattr("local_speech_to_text.daemon.notify", lambda *a, **k: None)
    return d


class FakeVosk:
    last = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        FakeVosk.last = self
        self.started = False

    def start(self):
        self.started = True
        return True


class FakeOWW(FakeVosk):
    pass


def _install(monkeypatch, name, cls):
    monkeypatch.setattr(wakeword, name, cls)


def test_daemon_usa_vosk_con_frase(monkeypatch):
    _install(monkeypatch, "find_vosk_model", lambda path="": Path("/models/vosk"))
    _install(monkeypatch, "VoskMonitor", FakeVosk)
    d = _daemon(monkeypatch, wake_word=True, wake_word_engine="vosk",
                wake_word_phrase="dev paul")

    d._maybe_start_wake_word()

    assert isinstance(d.wake_monitor, FakeVosk)
    assert d.wake_monitor.started is True
    assert d.wake_monitor.kwargs["phrase"] == "dev paul"
    assert d.wake_monitor.kwargs["model_path"] == "/models/vosk"


def test_daemon_vosk_sin_modelo_no_arranca(monkeypatch, capsys):
    _install(monkeypatch, "find_vosk_model", lambda path="": None)
    _install(monkeypatch, "VoskMonitor", FakeVosk)
    d = _daemon(monkeypatch, wake_word=True, wake_word_engine="vosk")

    d._maybe_start_wake_word()

    assert d.wake_monitor is None
    assert "wakeword --download-vosk" in capsys.readouterr().out


def test_daemon_openwakeword_sigue_siendo_el_default(monkeypatch):
    _install(monkeypatch, "resolve_model_path", lambda name: "/models/hey.onnx")
    _install(monkeypatch, "WakeWordMonitor", FakeOWW)
    d = _daemon(monkeypatch, wake_word=True)

    d._maybe_start_wake_word()

    assert isinstance(d.wake_monitor, FakeOWW)
    assert d.wake_monitor.kwargs["threshold"] == d.config.wake_word_threshold
