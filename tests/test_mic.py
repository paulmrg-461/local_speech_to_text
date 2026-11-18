from local_speech_to_text.config import Config
from local_speech_to_text.recorder import AudioRecorder

FAKE_DEVICES = [
    {"name": "HDA NVidia: HDMI (0 in)", "max_input_channels": 0},
    {"name": "FaceCam 1000X: USB Audio (1 in)", "max_input_channels": 1},
    {"name": "HD-Audio Generic: ALC1220 Analog (2 in)", "max_input_channels": 2},
]


def _recorder_with_fake_sd(monkeypatch, mic):
    from local_speech_to_text import recorder as rec_mod

    class FakeSD:
        @staticmethod
        def query_devices():
            return FAKE_DEVICES

    monkeypatch.setattr(rec_mod, "sd", FakeSD, raising=False)
    return AudioRecorder(mic=mic)


def test_resolve_mic_por_substring(monkeypatch):
    r = _recorder_with_fake_sd(monkeypatch, "facecam")
    assert r.resolve_mic() == 1


def test_resolve_mic_case_insensitive(monkeypatch):
    r = _recorder_with_fake_sd(monkeypatch, "ALC1220")
    assert r.resolve_mic() == 2


def test_resolve_mic_none_usa_default(monkeypatch):
    r = _recorder_with_fake_sd(monkeypatch, None)
    assert r.resolve_mic() is None
    r2 = _recorder_with_fake_sd(monkeypatch, "")
    assert r2.resolve_mic() is None


def test_resolve_mic_sin_match_warns_y_default(monkeypatch, capsys):
    r = _recorder_with_fake_sd(monkeypatch, "noexiste")
    assert r.resolve_mic() is None
    assert "usando el default" in capsys.readouterr().out


def test_resolve_mic_ignora_dispositivos_sin_entrada(monkeypatch):
    r = _recorder_with_fake_sd(monkeypatch, "hda")
    assert r.resolve_mic() is None  # 'HDA NVidia HDMI' tiene 0 canales de entrada


def test_config_mic_desde_toml_y_env(monkeypatch, tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('mic = "FaceCam"\n')
    cfg = Config.load(config_file=cfg_file)
    assert cfg.mic == "FaceCam"
    monkeypatch.setenv("LOCAL_STT_MIC", "ALC1220")
    cfg2 = Config.load(config_file=cfg_file)
    assert cfg2.mic == "ALC1220"  # env gana
