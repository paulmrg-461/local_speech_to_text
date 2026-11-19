from pathlib import Path

from local_speech_to_text.config import Config, default_config_path


def test_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    for var in ("LOCAL_STT_MODEL", "LOCAL_STT_LANG", "LOCAL_STT_DEVICE", "LOCAL_STT_COMPUTE",
                "LOCAL_STT_BEAM", "LOCAL_STT_AUTO_PASTE", "LOCAL_STT_SILENCE_STOP"):
        monkeypatch.delenv(var, raising=False)
    cfg = Config.load()
    assert cfg.model == "large-v3-turbo"
    assert cfg.device == "cuda"
    assert cfg.auto_paste is True
    assert cfg.silence_stop is False


def test_env_gana_sobre_toml(monkeypatch, tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('model = "small"\nbeam_size = 1\nsilence_stop = true\n')
    monkeypatch.setenv("LOCAL_STT_MODEL", "medium")
    cfg = Config.load(config_file=cfg_file)
    assert cfg.model == "medium"  # env gana
    assert cfg.beam_size == 1  # del toml
    assert cfg.silence_stop is True


def test_lang_auto_es_none(monkeypatch):
    monkeypatch.setenv("LOCAL_STT_LANG", "auto")
    cfg = Config.load(config_file=Path("/no/existe.toml"))
    assert cfg.language is None


def test_cli_no_pisa_language_sin_flag(monkeypatch, tmp_path):
    """Sin --lang, env/TOML deben ganar (antes el default 'es' los pisaba)."""
    from argparse import Namespace

    from local_speech_to_text.cli import _config_from_args

    monkeypatch.setenv("LOCAL_STT_LANG", "en")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    args = Namespace(model=None, lang=None, device=None, compute=None)
    assert _config_from_args(args).language == "en"

    args.lang = "auto"
    assert _config_from_args(args).language is None

    args.lang = "es"
    assert _config_from_args(args).language == "es"


def test_override_cli_gana_sobre_todo(monkeypatch, tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('model = "small"\n')
    monkeypatch.setenv("LOCAL_STT_MODEL", "medium")
    cfg = Config.load(config_file=cfg_file, model="tiny")
    assert cfg.model == "tiny"


def test_toml_ignora_claves_desconocidas(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('hack = true\nmodel = "base"\n')
    cfg = Config.load(config_file=cfg_file)
    assert cfg.model == "base"


def test_bool_de_env(monkeypatch):
    monkeypatch.setenv("LOCAL_STT_AUTO_PASTE", "0")
    monkeypatch.setenv("LOCAL_STT_SILENCE_STOP", "1")
    cfg = Config.load(config_file=Path("/no/existe.toml"))
    assert cfg.auto_paste is False
    assert cfg.silence_stop is True


def test_default_config_path_respeta_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert default_config_path() == tmp_path / "local-stt" / "config.toml"
