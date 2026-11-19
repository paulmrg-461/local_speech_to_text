import io


from local_speech_to_text.config_tui import _render, _load_current, run_tui


def test_render_bools_ints_y_strings():
    out = _render({
        "model": "large-v3-turbo",
        "language": "es",
        "auto_paste": True,
        "beam_size": 5,
        "stream_window": 12.0,
    })
    assert 'model = "large-v3-turbo"' in out
    assert 'language = "es"' in out
    assert "auto_paste = true" in out
    assert "beam_size = 5" in out
    assert "stream_window = 12.0" in out


def test_render_conserva_tablas_desconocidas():
    out = _render({
        "model": "tiny",
        "app_vocab": {"code|vscode": "vocab-ide.txt"},
    })
    assert "[app_vocab]" in out
    assert '"code|vscode" = "vocab-ide.txt"' in out


def test_render_conserva_hold_devices():
    """El TUI no edita la allowlist pero no debe comentarla al guardar."""
    out = _render({"push_to_talk": True, "hold_devices": ["AT Translated", "Logitech"]})
    assert 'hold_devices = ["AT Translated", "Logitech"]' in out
    assert "# (sin soporte TUI) hold_devices" not in out
    assert "hold_devices = []" in _render({"hold_devices": []})


def test_ask_lista_parsea_comas(monkeypatch):
    from local_speech_to_text.config_tui import _ask

    monkeypatch.setattr("builtins.input", lambda *a, **k: "AT Translated, Logitech")
    assert _ask("Teclados", "list", [], None) == ["AT Translated", "Logitech"]

    monkeypatch.setattr("builtins.input", lambda *a, **k: "")
    assert _ask("Teclados", "list", ["X"], None) == ["X"]


def test_render_no_duplica_hold_devices():
    out = _render({"hold_devices": ["A"]})
    assert out.count("hold_devices =") == 1


def test_run_tui_sin_tty_solo_muestra(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))  # isatty False en StringIO
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('model = "small"\nauto_paste = false\n')
    rc = run_tui(cfg_file)
    out = capsys.readouterr().out
    assert rc == 1
    assert 'model = "small"' in out
    assert "auto_paste = false" in out
    # no reescribe
    assert "Generado por" not in cfg_file.read_text()


def test_run_tui_con_tty_guarda_solo_si_cambia(monkeypatch, tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('model = "small"\napp_vocab = {code = "v.txt"}\n')

    class FakeTTY(io.StringIO):
        def isatty(self):
            return True

    # respuestas: model=1 (base), resto Enter
    answers = iter(["1"] + [""] * 40)
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(answers))
    monkeypatch.setattr("sys.stdin", FakeTTY(""))

    rc = run_tui(cfg_file)
    assert rc == 0
    saved = _load_current(cfg_file)
    assert saved["model"] == "base"  # índice 1 de la lista de modelos
    assert "auto_paste" not in saved  # Enter sobre una clave ausente: no se materializa
    assert saved["app_vocab"]["code"] == "v.txt"  # conservada


def test_run_tui_sin_cambios_no_reescribe(monkeypatch, tmp_path):
    cfg_file = tmp_path / "config.toml"
    original_text = '# comentario bonito\nmodel = "small"\n'
    cfg_file.write_text(original_text)

    class FakeTTY(io.StringIO):
        def isatty(self):
            return True

    answers = iter([""] * 60)
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(answers))
    monkeypatch.setattr("sys.stdin", FakeTTY(""))

    run_tui(cfg_file)
    assert cfg_file.read_text() == original_text  # intacto
