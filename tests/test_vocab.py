
from local_speech_to_text.vocab import apply_corrections, load_corrections, load_vocabulary


def test_vocab_vacio_si_no_existe(tmp_path):
    assert load_vocabulary(tmp_path / "nope.txt") == ""


def test_vocab_dedup_y_comentarios(tmp_path):
    f = tmp_path / "vocabulary.txt"
    f.write_text("# nombres propios\nDevPaul\nFastAPI\nDevPaul\n RTX 5070 \n")
    assert load_vocabulary(f) == "DevPaul, FastAPI, RTX 5070"


def test_vocab_trunca_a_200(tmp_path):
    f = tmp_path / "vocabulary.txt"
    f.write_text("\n".join(f"terminolarguísimo{i}" for i in range(30)))
    assert len(load_vocabulary(f)) <= 200


def test_corrections_formato(tmp_path):
    f = tmp_path / "corrections.txt"
    f.write_text("# reglas\nya que -> Yago\ndev pablo -> DevPaul\nmalformada sin flecha\nx -> y\n")
    rules = load_corrections(f)
    assert rules == [("ya que", "Yago"), ("dev pablo", "DevPaul"), ("x", "y")]


def test_apply_corrections_caso_insensible(tmp_path):
    assert apply_corrections("El ya que programó mucho", [("ya que", "Yago")]) == "El Yago programó mucho"
    # mantiene mayúscula inicial
    assert apply_corrections("ya que es rápido", [("ya que", "yago")]) == "Yago es rápido"


def test_apply_corrections_respeto_limites_de_palabra():
    assert apply_corrections("el core del asunto", [("core", "kernel")]) == "el kernel del asunto"
    assert apply_corrections("recordar y acordarse", [("cuerda", "acuerdo")]) == "recordar y acordarse"


def test_apply_corrections_multiples_reglas():
    text = "dev pablo usa fast api"
    rules = [("dev pablo", "DevPaul"), ("fast api", "FastAPI")]
    assert apply_corrections(text, rules) == "DevPaul usa FastAPI"
