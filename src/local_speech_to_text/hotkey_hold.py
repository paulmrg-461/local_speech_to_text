"""Push-to-talk: chord, máquina de estados y (opcional) listener evdev.

La lógica pura (parser + máquina) no importa `evdev`: CI y usuarios sin el
extra `[hold]` pueden ejecutar los tests. La fuente real se importa de forma
lazy en `EvdevSource`.

Diseño: docs/specs/push-to-talk/design.md
"""

from __future__ import annotations

import threading
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


@dataclass(frozen=True)
class KeyEvent:
    """Evento normalizado de un teclado (nunca se registran códigos ajenos)."""

    key: str  # "KEY_F"
    value: int  # 1 press, 0 release, 2 auto-repeat
    device: str = ""


def device_matches(name: str, allowlist: tuple[str, ...] | list[str] = ()) -> bool:
    """True si el nombre del teclado pasa la allowlist (substring, sin mayúsculas)."""
    if not allowlist:
        return True
    low = (name or "").lower()
    return any(entry.lower() in low for entry in allowlist if entry)


class EventSource:
    """Interfaz mínima para poder testear sin evdev."""

    def open(self) -> str | None:  # None = ok; si no, motivo
        raise NotImplementedError

    def poll(self, timeout: float) -> list[KeyEvent]:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class EvdevSource(EventSource):
    """Lee `/dev/input/event*` en solo lectura (sin EVIOCGRAB).

    Requiere el extra `[hold]` (python-evdev) y permiso de lectura: el usuario
    debe pertenecer al grupo `input`.
    """

    def __init__(self, watched_keys: set[str], allowlist: tuple[str, ...] | list[str] = ()):
        self._watched = watched_keys
        self._allowlist = tuple(allowlist)
        self._devices: dict[str, object] = {}
        self._codes: set[int] = set()
        self._last_scan = 0.0
        self._evdev = None
        self._ecodes = None

    def open(self) -> str | None:
        try:
            import evdev
            from evdev import ecodes
        except ImportError:
            return "no-evdev"
        self._evdev = evdev
        self._ecodes = ecodes
        self._codes = {getattr(ecodes, name) for name in self._watched if hasattr(ecodes, name)}
        denied = self._discover()
        if not self._devices:
            return "no-permission" if denied else "no-devices"
        return None

    def _discover(self) -> bool:
        """Abre teclados nuevos. Devuelve True si alguno dio PermissionError."""
        import glob

        denied = False
        # list_devices() filtra por permisos y ocultaría el motivo real: con
        # el usuario fuera de `input` hay devices que existen pero no se leen.
        for path in sorted(glob.glob("/dev/input/event*")):
            if path in self._devices:
                continue
            try:
                dev = self._evdev.InputDevice(path, readonly=True)
            except PermissionError:
                denied = True
                continue
            except Exception:
                continue
            try:
                if not device_matches(dev.name or "", self._allowlist):
                    dev.close()
                    continue
                caps = dev.capabilities().get(self._ecodes.EV_KEY, [])
                if not ({self._ecodes.KEY_F, self._ecodes.KEY_A} & set(caps)):
                    dev.close()
                    continue
            except Exception:
                try:
                    dev.close()
                except Exception:
                    pass
                continue
            self._devices[path] = dev
            print(f"[hold] teclado: {dev.name} ({path})")
        return denied

    def _drop(self, path: str) -> None:
        dev = self._devices.pop(path, None)
        if dev is not None:
            try:
                dev.close()
            except Exception:
                pass

    def poll(self, timeout: float) -> list[KeyEvent]:
        from select import select

        if not self._devices:
            return []
        events: list[KeyEvent] = []
        try:
            readable, _, _ = select(list(self._devices.values()), [], [], timeout)
        except (OSError, ValueError):
            readable = []
        for dev in readable:
            try:
                batch = dev.read()
            except OSError:  # desconectado
                self._drop(dev.path)
                continue
            for ev in batch:
                if ev.type != self._ecodes.EV_KEY or ev.code not in self._codes:
                    continue
                name = self._ecodes.KEY.get(ev.code, "")
                if name:
                    events.append(KeyEvent(name, ev.value, dev.name or ""))
        # Hotplug: los event* cambian al reconectar teclados.
        now = time.monotonic()
        if now - self._last_scan > 5.0:
            self._last_scan = now
            self._discover()
        return events

    def close(self) -> None:
        for path in list(self._devices):
            self._drop(path)


class HotkeyListener:
    """Hilo que traduce press/release del chord en start/stop del dictado."""

    def __init__(
        self,
        chord: HoldChord,
        min_ms: int = 200,
        allowlist: tuple[str, ...] | list[str] = (),
        on_start: Callable[[], None] | None = None,
        on_stop: Callable[[], None] | None = None,
        source: EventSource | None = None,
        on_status: Callable[[str], None] | None = None,
    ):
        self.chord = chord
        self.machine = HoldStateMachine(chord, min_ms=min_ms, on_start=on_start, on_stop=on_stop)
        self._source = source or EvdevSource(
            watched_keys={chord.key, *MODIFIER_KEYS}, allowlist=allowlist
        )
        self._on_status = on_status
        self._mods: set[str] = set()
        self._stop = threading.Event()
        self._thread = None
        self.status = "stopped"

    def _set_status(self, status: str) -> None:
        self.status = status
        if self._on_status is not None:
            self._on_status(status)

    def start(self) -> bool:
        reason = self._source.open()
        if reason:
            self._set_status(reason)
            print(f"[hold] push-to-talk no disponible: {reason}")
            return False
        self._set_status("running")
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[hold] push-to-talk activo: mantén {self.chord.text} para dictar")
        return True

    def handle_event(self, event: KeyEvent) -> None:
        """Procesa un evento. Filtra auto-repeat y códigos no vigilados (RS-2)."""
        if event.value == 2:
            return
        if event.key in MODIFIER_KEYS:
            group = MODIFIER_KEYS[event.key]
            if event.value == 0:
                self._mods.discard(group)
                # Soltar el modificador antes que la tecla también termina el hold.
                if self.machine.state == ARMED and not self.chord.matches(self.chord.key, self._mods):
                    self.machine.release()
            else:
                self._mods.add(group)
            return
        if event.key != self.chord.key:
            return
        if event.value == 1 and self.chord.matches(event.key, self._mods):
            self.machine.press()
        elif event.value == 0:
            self.machine.release()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                for event in self._source.poll(0.5):
                    self.handle_event(event)
            except Exception as e:  # un fallo no debe tumbar el daemon
                print(f"[hold] error leyendo teclado: {e}")
                self._stop.wait(1.0)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        self._source.close()
        self._set_status("stopped")
