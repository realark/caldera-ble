"""Transport-agnostic codec for the Relaxe Caldera sauna ASCII protocol.

Pure functions and dataclasses only — no I/O, no Bluetooth. This is the single
source of truth for encoding commands and decoding status frames, reusable by
both the ``bleak`` device layer and the Home Assistant integration, and fully
unit-testable without hardware. See ``PROTOCOL.md`` for the wire format.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

# Commands are ASCII, framed ``X…Z`` and terminated with CRLF.
LINE_TERMINATOR = b"\r\n"

# Status frames are ASCII, framed lowercase ``x…z``, at least this long.
STATUS_MIN_LEN = 15

# Timer limits (minutes) are the same across all known models.
TIMER_MIN = 5
TIMER_MAX = 60


class Color(IntEnum):
    """RGB mood-light presets (command ``XCL0<n>Z`` / status index 3).

    Names are the colors actually observed on the hardware — the OEM app's
    labels are scrambled (see PROTOCOL.md). Index 8 is a preset the app never
    exposes; index 9 is a firmware no-op and is intentionally not a member.
    """

    WHITE = 0
    YELLOW = 1
    GREEN = 2
    CYAN = 3
    BLUE = 4
    PURPLE = 5
    RED = 6
    CHANGING = 7  # cycles through colors
    GRADUALLY = 8  # fades between colors


class AudioSource(IntEnum):
    NONE = 0
    BLUETOOTH = 1
    USB = 2


class TempUnit(IntEnum):
    FAHRENHEIT = 0
    CELSIUS = 1


# Per-model temperature limits, keyed by model id. Model is derived from the
# advertised name (see ``model_from_name``). Values are (unit -> (min, max)).
_TEMP_LIMITS: dict[int, dict[TempUnit, tuple[int, int]]] = {
    0: {TempUnit.CELSIUS: (30, 70), TempUnit.FAHRENHEIT: (86, 158)},
    1: {TempUnit.CELSIUS: (30, 70), TempUnit.FAHRENHEIT: (86, 158)},
    2: {TempUnit.CELSIUS: (30, 75), TempUnit.FAHRENHEIT: (86, 167)},
    3: {TempUnit.CELSIUS: (18, 65), TempUnit.FAHRENHEIT: (64, 149)},
}


def model_from_name(name: str | None) -> int:
    """Map an advertised device name to the app's model id.

    Mirrors the (case-sensitive) checks in the OEM app's ``MainActivity``.
    """
    if not name:
        return 0
    if "BTSauna" in name:
        return 0
    if "SAUNA" in name:
        return 1
    if "GHS-Sauna" in name:
        return 2
    if "Sauna-A1-" in name:
        return 3
    return 0


def temp_limits(model: int, unit: TempUnit) -> tuple[int, int]:
    """Return (min, max) target temperature for a model in the given unit."""
    return _TEMP_LIMITS.get(model, _TEMP_LIMITS[0])[unit]


def _hexpair(value: int) -> str:
    """Encode a byte as two uppercase hex chars, the way the app does.

    Note this is the raw hex value, not BCD: 45 -> ``"2D"``, 158 -> ``"9E"``.
    """
    if not 0 <= value <= 255:
        raise ValueError(f"value {value} out of range 0..255")
    return f"{value:02X}"


def _frame(body: str) -> bytes:
    """Wrap a command body as ``X<body>Z`` + CRLF, as ASCII bytes."""
    return f"X{body}Z".encode("ascii") + LINE_TERMINATOR


# --- Command builders -------------------------------------------------------
# Each returns the exact bytes to write to the FFF1 characteristic.


def cmd_power(on: bool) -> bytes:
    return _frame("SWON" if on else "SWOF")


def cmd_lamp(on: bool) -> bytes:
    return _frame("L1ON" if on else "L1OF")


def cmd_color_light(on: bool) -> bytes:
    return _frame("CLON" if on else "CLOF")


def cmd_set_color(color: Color | int) -> bytes:
    n = int(color)
    if not 0 <= n <= 8:
        raise ValueError(f"color index {n} out of range 0..8")
    return _frame(f"CL0{n}")


def cmd_set_target_temp(value: int) -> bytes:
    """Set target temperature (in whatever unit the sauna is currently in)."""
    return _frame(f"T1{_hexpair(value)}")


def cmd_set_timer(minutes: int) -> bytes:
    return _frame(f"TM{_hexpair(minutes)}")


def cmd_unit_c_to_f() -> bytes:
    return _frame("CTOF")


def cmd_unit_f_to_c() -> bytes:
    return _frame("FTOC")


def cmd_audio_bluetooth() -> bytes:
    return _frame("MU01")


def cmd_audio_usb() -> bytes:
    return _frame("MU02")


def cmd_audio_off() -> bytes:
    return _frame("MUOF")


def cmd_volume_up() -> bytes:
    return _frame("VLIC")


def cmd_volume_down() -> bytes:
    return _frame("VLDC")


def cmd_track_next() -> bytes:
    return _frame("CHIC")


def cmd_track_prev() -> bytes:
    return _frame("CHDC")


# --- Status decoding --------------------------------------------------------


@dataclass(frozen=True)
class SaunaState:
    """Decoded snapshot from a status frame."""

    power: bool
    lamp: bool
    color_on: bool
    color: Color | None  # active preset when known, else None
    audio: AudioSource
    unit: TempUnit
    current_temp: int
    target_temp: int
    timer_minutes: int
    error: int
    raw: str

    @property
    def ok(self) -> bool:
        return self.error == 0


def _hexdigit(c: str) -> int:
    v = "0123456789abcdef".find(c.lower())
    if v < 0:
        raise ValueError(f"bad hex digit {c!r}")
    return v


def _hexbyte(s: str, i: int) -> int:
    return _hexdigit(s[i]) * 16 + _hexdigit(s[i + 1])


def parse_status(data: bytes | str) -> SaunaState | None:
    """Decode a status frame, or return None if it isn't a valid one.

    Accepts raw bytes (as received over BLE) or a decoded string. Returns None
    for anything that fails the ``x…z`` framing / length check, matching the
    app's tolerant behaviour (it also ignores non-status chatter).
    """
    if isinstance(data, (bytes, bytearray)):
        text = bytes(data).decode("ascii", "replace")
    else:
        text = data
    s = text.strip()
    if len(s) < STATUS_MIN_LEN or s[0] != "x" or s[-1] != "z":
        return None
    try:
        power = s[1] == "o"
        lamp = s[2] == "o"
        c3 = s[3]
        if c3 == "o":
            color_on, color = True, None
        elif c3 == "f":
            color_on, color = False, None
        elif c3.isdigit():
            color_on = True
            try:
                color = Color(int(c3))
            except ValueError:
                color = None  # a preset index we don't have a name for
        else:
            color_on, color = False, None
        audio = {"1": AudioSource.BLUETOOTH, "2": AudioSource.USB}.get(
            s[4], AudioSource.NONE
        )
        unit = TempUnit.CELSIUS if s[6] == "1" else TempUnit.FAHRENHEIT
        current_temp = _hexbyte(s, 7)
        timer_minutes = _hexbyte(s, 9)
        target_temp = _hexbyte(s, 11)
        error = int(s[13])
    except (ValueError, IndexError):
        return None
    return SaunaState(
        power=power,
        lamp=lamp,
        color_on=color_on,
        color=color,
        audio=audio,
        unit=unit,
        current_temp=current_temp,
        target_temp=target_temp,
        timer_minutes=timer_minutes,
        error=error,
        raw=s,
    )
