from __future__ import annotations

import re

"""Post-procesado de dictado: comandos hablados de puntuación y limpieza.

Whisper large-v3-turbo ya puntúa al dictar, pero los comandos hablados
("punto y coma", "nueva línea") suelen transcribirse como texto literal.
Aquí se convierten a su signo y se normaliza espaciado/mayúsculas.

Se desactiva con LOCAL_STT_DICTATION_COMMANDS=0.
"""

# (regex, reemplazo). Orden importa: lo más específico va primero.
_RULES: list[tuple[str, str]] = [
    # combinaciones frecuentes de cierre + puntuación
    (r"\s*cerrar comillas punto\b", '".'),
    (r"\s*cerrar comillas coma\b", '",'),
    (r"\s*cerrar paréntesis punto\b", ")."),
    (r"\s*cerrar paréntesis coma\b", "),"),
    (r"\s*punto y coma\b", ";"),
    (r"\s*punto y aparte\b", ".\n"),
    (r"\s*punto final\b", "."),
    (r"\s*dos puntos\b", ":"),
    (r"\s*punto\b", "."),
    (r"\s*coma\b", ","),
    (r"\s*nueva línea\b|\s*salto de línea\b", "\n"),
    (r"\s*abrir paréntesis\b", " ("),
    (r"\s*cerrar paréntesis\b", ")"),
    (r"\s*abrir comillas\b", ' "'),
    (r"\s*cerrar comillas\b", '"'),
    (r"\s*signo de interrogación\b", "?"),
    (r"\s*abrir exclamación\b|\s*signo de exclamación\b", "¡"),
    (r"\s*cerrar exclamación\b", "!"),
    (r"\s*(?:guion|guión)\b\s*", "-"),
    (r"\s*barra\b\s*", "/"),
    (r"\s*arroba\b\s*", "@"),
]

_PUNCT = ".,;:!?)»"


def _apply_rules(text: str) -> str:
    for pattern, repl in _RULES:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    return text


def _fix_spacing(text: str) -> str:
    text = re.sub(r"\s+([%s])" % re.escape(_PUNCT), r"\1", text)  # espacio antes de signo de cierre
    text = re.sub(r"([-\u2014/])\s+(\w)", r"\1\2", text)  # espacio tras guion/barra
    text = re.sub(r"([(¡¿«\u201c\"])\s+", r"\1", text)  # espacio después de abrir
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    return text.strip()


def _capitalize_sentences(text: str) -> str:
    def _cap(match: re.Match[str]) -> str:
        return match.group(1) + match.group(2) + match.group(3).upper()

    return re.sub(r"(^|[.!?]\s*|\n\s*)((?:[(\"¡¿«']\s*)*)(\w)", _cap, text)


_PORCIENTO = "PORCIENTOGUARD"


def numbers_to_digits(text: str) -> str:
    """Convierte números hablados a dígitos ('tres coma catorce' -> '3,14').

    Protege 'por ciento' (text2num lo leería como parte del número: 'ciento y
    tres') y lo convierte a '%' tras el dígito. Requiere el paquete text2num;
    si no está, devuelve el texto sin tocar.
    """
    try:
        from text_to_num import alpha2digit
    except ImportError:
        return text
    guarded = re.sub(r"\bpor ciento\b", _PORCIENTO, text, flags=re.IGNORECASE)
    try:
        out = alpha2digit(guarded, lang="es")
    except Exception:
        return text
    out = out.replace(_PORCIENTO, "por ciento")
    return re.sub(r"(\d)\s+por ciento\b", r"\1 %", out, flags=re.IGNORECASE)


def clean_text(text: str) -> str:
    """Convierte comandos hablados en puntuación y normaliza el texto."""
    if not text:
        return text
    return _capitalize_sentences(_fix_spacing(_apply_rules(text))).strip()
