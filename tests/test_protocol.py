"""Unit tests for the sauna codec — no hardware required.

The golden status frame and its decoding come from a real capture of the
``Sauna-BLE`` unit (see PROTOCOL.md / scripts/probe.py).
"""
import pytest

from caldera_sauna import protocol as p
from caldera_sauna.protocol import AudioSource, Color, TempUnit

# --- Command encoding -------------------------------------------------------


def test_power():
    assert p.cmd_power(True) == b"XSWONZ\r\n"
    assert p.cmd_power(False) == b"XSWOFZ\r\n"


def test_lamp():
    assert p.cmd_lamp(True) == b"XL1ONZ\r\n"
    assert p.cmd_lamp(False) == b"XL1OFZ\r\n"


def test_color_light_onoff():
    assert p.cmd_color_light(True) == b"XCLONZ\r\n"
    assert p.cmd_color_light(False) == b"XCLOFZ\r\n"


# The app uses 0..7; hardware also has a hidden preset at 8. Index 9 is a no-op.
@pytest.mark.parametrize("n", range(9))
def test_set_color(n):
    assert p.cmd_set_color(n) == f"XCL0{n}Z\r\n".encode()


def test_set_color_enum_and_bounds():
    assert p.cmd_set_color(Color.GREEN) == b"XCL04Z\r\n"
    with pytest.raises(ValueError):
        p.cmd_set_color(9)


def test_set_target_temp_hex_not_bcd():
    # 45 -> 0x2D, 158 -> 0x9E (raw hex, matching the app).
    assert p.cmd_set_target_temp(45) == b"XT12DZ\r\n"
    assert p.cmd_set_target_temp(158) == b"XT19EZ\r\n"


def test_set_timer():
    assert p.cmd_set_timer(30) == b"XTM1EZ\r\n"
    assert p.cmd_set_timer(5) == b"XTM05Z\r\n"


def test_temp_out_of_range():
    with pytest.raises(ValueError):
        p.cmd_set_target_temp(256)


def test_units_and_audio():
    assert p.cmd_unit_c_to_f() == b"XCTOFZ\r\n"
    assert p.cmd_unit_f_to_c() == b"XFTOCZ\r\n"
    assert p.cmd_audio_bluetooth() == b"XMU01Z\r\n"
    assert p.cmd_audio_usb() == b"XMU02Z\r\n"
    assert p.cmd_audio_off() == b"XMUOFZ\r\n"


def test_volume_and_track():
    assert p.cmd_volume_up() == b"XVLICZ\r\n"
    assert p.cmd_volume_down() == b"XVLDCZ\r\n"
    assert p.cmd_track_next() == b"XCHICZ\r\n"
    assert p.cmd_track_prev() == b"XCHDCZ\r\n"


# --- Status decoding --------------------------------------------------------


def test_parse_golden_frame():
    # Captured live: sauna off, Fahrenheit, target 158°F, timer 49min.
    st = p.parse_status(b"xfff01000319e0z")
    assert st is not None
    assert st.power is False
    assert st.lamp is False
    assert st.color_on is False
    assert st.audio is AudioSource.NONE
    assert st.unit is TempUnit.FAHRENHEIT
    assert st.current_temp == 0
    assert st.timer_minutes == 0x31 == 49
    assert st.target_temp == 0x9E == 158
    assert st.error == 0
    assert st.ok is True


def test_parse_all_on_celsius():
    # idx: 0'x' 1'o'power 2'o'lamp 3'4'color 4'1'bt 5'1'resv 6'1'celsius
    #      7-8 '2d'=45 cur, 9-10 '1e'=30 timer, 11-12 '46'=70 target, 13'0'err, 14'z'
    st = p.parse_status("xoo41112d1e460z")
    assert st is not None
    assert st.power and st.lamp
    assert st.color_on and st.color is Color.GREEN
    assert st.audio is AudioSource.BLUETOOTH
    assert st.unit is TempUnit.CELSIUS
    assert st.current_temp == 45
    assert st.timer_minutes == 30
    assert st.target_temp == 70


def test_parse_rejects_garbage():
    assert p.parse_status(b"") is None
    assert p.parse_status(b"hello world nope") is None
    assert p.parse_status("xshortz") is None
    assert p.parse_status("Xfff01000319e0z") is None  # wrong (upper) start
    assert p.parse_status("xfff01000319e0Q") is None  # wrong end


def test_error_code_surfaced():
    # 15 chars, error digit at index 13
    st = p.parse_status("xfff0000000003z")
    assert st is not None
    assert st.error == 3
    assert st.ok is False


# --- Model / limits ---------------------------------------------------------


def test_model_from_name():
    assert p.model_from_name("Sauna-BLE") == 0
    assert p.model_from_name("GHS-Sauna") == 2
    assert p.model_from_name("Sauna-A1-01") == 3
    assert p.model_from_name(None) == 0


def test_temp_limits():
    assert p.temp_limits(0, TempUnit.CELSIUS) == (30, 70)
    assert p.temp_limits(3, TempUnit.FAHRENHEIT) == (64, 149)
