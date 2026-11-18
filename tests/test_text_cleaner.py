from local_speech_to_text.text_cleaner import clean_text


def test_comandos_basicos_de_puntuacion():
    assert clean_text("hola coma qué tal punto") == "Hola, qué tal."


def test_punto_y_coma_y_dos_puntos():
    assert clean_text("primero punto y coma segundo dos puntos fin") == "Primero; segundo: fin"


def test_punto_y_aparte_y_nueva_linea():
    assert clean_text("párrafo uno punto y aparte párrafo dos") == "Párrafo uno.\nPárrafo dos"


def test_parentesis_y_comillas():
    assert clean_text("abrir paréntesis nota cerrar paréntesis") == "(Nota)"
    assert clean_text('abrir comillas cita cerrar comillas punto') == '"Cita".'  # punto fuera de comillas (español)


def test_interrogacion():
    assert clean_text("qué tal signo de interrogación") == "Qué tal?"


def test_no_rompe_texto_ya_puntuado():
    text = "Hola, esto ya está bien puntuado. ¿Verdad? ¡Sí!"
    assert clean_text(text) == text


def test_texto_vacio():
    assert clean_text("") == ""
    assert clean_text("   ") == ""


def test_capitaliza_tras_punto():
    assert clean_text("uno punto dos punto") == "Uno. Dos."


def test_guion_y_arroba():
    assert clean_text("dos guion tres") == "Dos-tres"
    assert clean_text("pablo arroba gmail punto com") == "Pablo@gmail. Com"


def test_espacios_normales():
    assert clean_text("hola   mundo punto") == "Hola mundo."
