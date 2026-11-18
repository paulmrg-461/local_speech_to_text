"""Push-to-talk: chord, máquina de estados y (opcional) listener evdev.

La lógica pura (parser + máquina) no importa `evdev`: CI y usuarios sin el
extra `[hold]` pueden ejecutar los tests. La fuente real se importa de forma
lazy en `EvdevSource`.

Diseño: docs/specs/push-to-talk/design.md
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

# Grupos canónicos de modificadores (los dos Meta cuentan como "meta").
MODIFIER_KEYS = {
    "KEY_LEFTMETA": "meta",
    "KEY_RIGHTMETA": "meta",
    "KEY_LEFTCTRL": "ctrl",
    "KEY_RIGHTCTRL": "ctrl",
    "KEY_LEFTALT": "alt",
    "KEY_RIGHTALT": "alt",
    "KEY_LEFTSHIFT": "shift",
    "KEY_RIGHTSHIFT": "shift",
}

_MODIFIER_ALIASES = {
    "meta": ("super", "meta", "win", "cmd", "logo"),
    "ctrl": ("ctrl", "control"),
    "alt": ("alt", "option"),
    "shift": ("shift",),
}

# Nombres legibles -> nombre de tecla en evdev (`KEY_*`).
_KEY_ALIASES = {
    "space": "KEY_SPACE",
    "espacio": "KEY_SPACE",
    "esc": "KEY_ESC",
    "escape": "KEY_ESC",
    "enter": "KEY_ENTER",
    "intro": "KEY_ENTER",
    "return": "KEY_ENTER",
    "tab": "KEY_TAB",
    "backspace": "KEY_BACKSPACE",
    "delete": "KEY_DELETE",
}

# Estados
IDLE = "idle"
ARMED = "armed"  # gesto en curso iniciado por hold
TAP_OPEN = "tap_open"  # el primer toque arrancó; el siguiente lo para
EXTERNAL = "external"  # grabación ajena al hold (toggle/wake/socket)

# Orígenes de grabación
ORIGIN_HOLD = "hold"


def _modifier_group(name: str) -> str | None:
    for group, aliases in _MODIFIER_ALIASES.items():
        if name in aliases:
            return group
    return None


def _key_name(name: str) -> str | None:
    alias = _KEY_ALIASES.get(name)
    if alias:
        return alias
    if len(name) == 1 and name.isalnum():
        return f"KEY_{name.upper()}"
    # f1..f24, kp1, etc. ya vienen como nombre de evdev sin prefijo
    if name.isidentifier():
        candidate = f"KEY_{name.upper()}"
        return candidate
    return None


@dataclass(frozen=True)
class HoldChord:
    """Chord normalizado: tecla `KEY_*` + grupos de modificadores."""

    key: str
    mods: frozenset[str] = field(default_factory=frozenset)
    text: str = ""

    def matches(self, key: str, mods: frozenset[str]) -> bool:
        """True si el evento es la tecla del chord con sus modificadores."""
        return key == self.key and self.mods <= mods


def parse_chord(text: str) -> HoldChord | None:
    """`"super+f"` -> `HoldChord(KEY_F, {"meta"})`. Inválido -> None."""
    if not text or not text.strip():
        return None
    parts = [p.strip().lower() for p in text.split("+")]
    if not all(parts) or len(parts) < 2:
        return None
    *mod_names, key_name = parts
    mods: set[str] = set()
    for name in mod_names:
        group = _modifier_group(name)
        if group is None:
            return None
        mods.add(group)
    key = _key_name(key_name)
    if key is None:
        return None
    canonical = "+".join([*sorted(mods), key_name])
    return HoldChord(key=key, mods=frozenset(mods), text=canonical)


class HoldStateMachine:
    """Decide start/stop a partir de press/release del chord.

    - `start` se emite en el press (latencia mínima, RF-1).
    - Un tap corto no emite `stop`: el dictado sigue (equivale al primer
      toggle). El siguiente tap sí lo para (`TAP_OPEN`).
    - Auto-repeat (`value=2`) se descarta antes de llegar aquí.
    - Si la grabación es ajena (`EXTERNAL`), el release se ignora (RF-5).
    """

    def __init__(
        self,
        chord: HoldChord,
        min_ms: int = 200,
        on_start: Callable[[], None] | None = None,
        on_stop: Callable[[], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.chord = chord
        self.min_ms = max(0, int(min_ms))
        self._on_start = on_start
        self._on_stop = on_stop
        self._clock = clock
        self.state = IDLE
        self._pressed_at = 0.0

    def press(self, now: float | None = None) -> None:
        now = self._clock() if now is None else now
        if self.state == EXTERNAL:
            return
        if self.state == IDLE:
            self._emit(self._on_start)
            self.state = ARMED
        # ARMED/TAP_OPEN: nuevo gesto (p. ej. tras un release perdido)
        self._pressed_at = now

    def release(self, now: float | None = None) -> None:
        now = self._clock() if now is None else now
        if self.state in (IDLE, EXTERNAL):
            return
        held_ms = (now - self._pressed_at) * 1000
        if self.state == ARMED and held_ms < self.min_ms:
            # Tap: el press ya arrancó; se deja grabando hasta el próximo tap.
            self.state = TAP_OPEN
            return
        self._emit(self._on_stop)
        self.state = IDLE

    def notify_recording_started(self, origin: str) -> None:
        """La grabación la inició otro canal: el hold no la controla."""
        if origin != ORIGIN_HOLD and self.state == IDLE:
            self.state = EXTERNAL

    def notify_recording_stopped(self) -> None:
        """Watchdog/stop externo: el release posterior no debe parar nada."""
        self.state = IDLE

    @staticmethod
    def _emit(callback: Callable[[], None] | None) -> None:
        if callback is not None:
            callback()
