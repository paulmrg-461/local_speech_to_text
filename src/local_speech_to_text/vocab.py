from __future__ import annotations

import re
from pathlib import Path

"""Vocabulario personalizado y correcciones.

- `vocabulary.txt`: un término por línea. Se pasa como `initial_prompt` a
  Whisper para sesgar la transcripción hacia tus nombres/términos propios
  (ej: "DevPaul", "FastAPI", "ydotool"). Máx ~200 caracteres.
- `corrections.txt`: líneas `mal -> bien` (separador literal ` -> `).
  Se aplican tras la transcripción con límites de palabra, sin distinguir
  mayúsculas. `#` para comentarios.
"""


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def load_vocabulary(path: Path) -> str:
    """Términos -> initial_prompt para Whisper (truncado a 200 chars)."""
    terms = _read_lines(path)
    prompt = ", ".join(dict.fromkeys(terms))  # dedup conservando orden
    return prompt[:200]


def load_corrections(path: Path) -> list[tuple[str, str]]:
    """Pares (incorrecto, correcto) desde corrections.txt."""
    rules: list[tuple[str, str]] = []
    for line in _read_lines(path):
        if " -> " in line:
            wrong, right = (part.strip() for part in line.split(" -> ", 1))
            if wrong and right:
                rules.append((wrong, right))
    return rules


def apply_corrections(text: str, rules: list[tuple[str, str]]) -> str:
    """Aplica correcciones con límites de palabra (case-insensitive).

    Mantiene la mayúscula inicial del original si la corrección empieza en minúscula.
    """
    for wrong, right in rules:
        pattern = re.compile(r"\b%s\b" % re.escape(wrong), flags=re.IGNORECASE)

        def _fix(match: re.Match[str], right: str = right) -> str:
            src = match.group(0)
            at_start = match.start() == 0
            if right and (src[0].isupper() or at_start):
                return right[0].upper() + right[1:]
            return right

        text = pattern.sub(_fix, text)
    return text
