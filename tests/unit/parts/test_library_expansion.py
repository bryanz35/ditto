import re
from typing import get_args

from backend.contracts.parts import PARTS_DIR, PinType, load_library

STARTER_PARTS = {
    "esp32_devkitc",
    "xiao_esp32s3_sense",
    "bme280_breakout",
    "soil_moisture_capacitive",
    "hc_sr04p",
    "pir_hc_sr501",
    "ds18b20_probe",
    "inmp441",
    "ssd1306_096_i2c",
    "ws2812b_ring_12",
    "button_tactile_6mm",
    "button_arcade_30mm",
    "ky040_encoder",
    "buzzer_passive",
    "vibration_motor_module",
    "servo_sg90",
    "max98357a",
    "speaker_40mm_4ohm",
    "relay_module_1ch",
}
# Refs are lowercase letters and digits, so the first underscore ends the ref.
PIN_MACRO = re.compile(r"\bPIN_([A-Z0-9]+)_([A-Za-z0-9_]+)\b")
PIN_LITERAL = re.compile(
    r"\b(?:pinMode|digitalWrite|digitalRead|analogRead|tone|attach)\s*\(\s*\d"
)


def test_every_starter_part_loads():
    assert STARTER_PARTS <= set(load_library().parts)


def test_every_pin_type_is_allowed():
    allowed = set(get_args(PinType))
    for part in load_library().parts.values():
        assert {p.type for p in part.pins} <= allowed, part.id


def test_every_non_board_part_has_a_snippet_except_passive_ones():
    for part in load_library().parts.values():
        if part.category != "mcu" and part.pins:
            assert part.snippet, part.id


def test_lib_deps_use_platformio_owner_name_form():
    for part in load_library().parts.values():
        for dep in part.pio_lib_deps:
            assert re.fullmatch(r"[\w.-]+/[\w .-]+", dep), (part.id, dep)


def test_snippets_follow_the_pin_macro_convention():
    for part in load_library().parts.values():
        if not part.snippet:
            continue
        code = (PARTS_DIR / part.snippet).read_text()
        assert '#include "pins.h"' in code, part.snippet
        assert 'Serial.println("P2D_READY")' in code, part.snippet
        assert not PIN_LITERAL.search(code), part.snippet
        macros = PIN_MACRO.findall(code)
        assert macros, part.snippet
        assert len({ref for ref, _ in macros}) == 1, (part.snippet, macros)
        pins = {p.name.upper(): p.name for p in part.pins}
        assert {pin for _, pin in macros} <= set(pins), (part.snippet, macros)
