from pathlib import Path

from local_speech_to_text.active_window import match_profile
from local_speech_to_text.config import Config, _resolve_vocab

PROFILES = {
    "code|jetbrains|vscode|nvim|terminal": "vocab-ide.txt",
    "whatsapp|telegram": "vocab-chat.txt",
}


def test_match_profile_por_regex():
    assert match_profile("main.rs — jetbrains-rust", PROFILES) == "vocab-ide.txt"
    assert match_profile("WhatsApp (3 mensajes)", PROFILES) == "vocab-chat.txt"


def test_match_profile_sin_match():
    assert match_profile("Firefox: noticias", PROFILES) is None


def test_match_profile_ventana_none():
    assert match_profile(None, PROFILES) is None


def test_match_profile_regex_invalida_no_explota():
    assert match_profile("kate", {"[invalid": "x.txt"}) is None


def test_match_profile_case_insensitive():
    assert match_profile("VSCode — main.py", PROFILES) == "vocab-ide.txt"


def test_resolve_vocab_relativo_contra_config_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert _resolve_vocab("vocab-ide.txt") == tmp_path / "local-stt" / "vocab-ide.txt"


def test_resolve_vocab_absoluto_se_respeta(tmp_path):
    assert _resolve_vocab(str(tmp_path / "a.onnx")) == tmp_path / "a.onnx"


def test_config_app_vocab_desde_toml(monkeypatch, tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        '[app_vocab]\n"code|jetbrains" = "vocab-ide.txt"\n"whatsapp" = "vocab-chat.txt"\n'
    )
    cfg = Config.load(config_file=cfg_file)
    assert cfg.app_vocab["code|jetbrains"] == "vocab-ide.txt"
    assert match_profile("JetBrains Rider", cfg.app_vocab) == "vocab-ide.txt"


def test_config_app_vocab_vacio_por_defecto():
    assert Config.load(config_file=Path("/no/existe.toml")).app_vocab == {}
