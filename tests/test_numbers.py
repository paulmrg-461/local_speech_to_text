from local_speech_to_text.text_cleaner import numbers_to_digits


def test_por_ciento_no_se_fusiona_con_numeros():
    # el bug que motiva el guard: "ciento y tres" no debe nacer de "por ciento y tres"
    out = numbers_to_digits("me das veinticinco por ciento y tres coma catorce")
    assert "25 %" in out
    assert "103" not in out
    assert "3,14" in out


def test_numeros_simples():
    assert numbers_to_digits("tengo tres gatos y dos mil quinientos euros") == \
        "tengo 3 gatos y 2500 euros"


def test_numeros_con_decimales():
    assert numbers_to_digits("mide uno coma setenta y cinco metros") == "mide 1,75 metros"


def test_texto_sin_numeros_no_cambia():
    assert numbers_to_digits("hola mundo sin numeros") == "hola mundo sin numeros"


def test_porciento_mayusculas():
    assert numbers_to_digits("El VEINTICINCO POR CIENTO de las veces") == "El 25 % de las veces"


def test_por_ciento_sin_numero_previo_no_toca():
    assert numbers_to_digits("el por ciento de la cuenta") == "el por ciento de la cuenta"
