import json
import re
from pathlib import Path

import pytest

from backend.contracts.parts import PartLibrary, load_library
from backend.contracts.spec import ProjectSpec
from backend.tools import validate_spec as module
from backend.tools.validate_spec import validate_spec

ROOT = Path(__file__).resolve().parents[3]
SPECS = ROOT / "fixtures" / "specs"
PLANT = SPECS / "plant_monitor.json"
INVALID = sorted((SPECS / "invalid").glob("*.json"))
LIB = load_library()


def spec_with(change=lambda d: None) -> ProjectSpec:
    d = json.loads(PLANT.read_text())
    change(d)
    return ProjectSpec.model_validate(d)


def conn(d: dict, ref: str, pin: str) -> dict:
    return next(
        c for c in d["connections"] if c["part_ref"] == ref and c["part_pin"] == pin
    )


def lib_with(part_id: str, **update) -> PartLibrary:
    parts = dict(LIB.parts)
    parts[part_id] = parts[part_id].model_copy(update=update)
    return PartLibrary(parts)


def codes(spec: ProjectSpec, lib: PartLibrary = LIB) -> set[str]:
    return {e.code for e in validate_spec(spec, lib).errors}


# ---------------------------------------------------------------- acceptance


@pytest.mark.parametrize(
    "path",
    [PLANT, ROOT / "fixtures/runs/plant_monitor/spec.json"],
    ids=lambda p: p.parent.name,
)
def test_plant_monitor_passes_with_no_errors_or_warnings(path):
    result = validate_spec(ProjectSpec.model_validate_json(path.read_text()), LIB)
    assert result.ok and result.errors == []


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.stem)
def test_invalid_fixture_fails_with_exactly_its_code(path):
    result = validate_spec(ProjectSpec.model_validate_json(path.read_text()), LIB)
    assert not result.ok
    assert {e.code for e in result.errors} == {path.stem}


MENTIONS = {
    "pin_conflict": ["buzzer1.SIG", "GPIO21"],
    "reserved_pin": ["buzzer1.SIG", "GPIO6"],
    "input_only_output": ["buzzer1.SIG", "GPIO35"],
    "voltage_mismatch": ["env1.VCC", "5V", "3V3"],
    "unconnected_pin": ["soil1.AOUT"],
    "unknown_part": ["buzzer1", "buzzer_active", "buzzer_passive"],
    "i2c_address_conflict": ["env3", "env1", "0x76"],
}


def test_every_invalid_fixture_has_expected_mentions():
    assert set(MENTIONS) == {p.stem for p in INVALID}


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.stem)
def test_messages_name_the_part_and_pin(path):
    result = validate_spec(ProjectSpec.model_validate_json(path.read_text()), LIB)
    (error,) = result.errors
    for text in MENTIONS[path.stem]:
        assert text in error.message
    assert error.field


def test_messages_list_free_alternatives():
    spec = ProjectSpec.model_validate_json(
        (SPECS / "invalid/reserved_pin.json").read_text()
    )
    (error,) = validate_spec(spec, LIB).errors
    free = error.message.split("free output pins: ")[1].split(", ")
    assert "GPIO4" in free
    for taken_or_bad in ("GPIO21", "GPIO22", "GPIO34", "GPIO6", "GPIO35", "GPIO2"):
        assert taken_or_bad not in free  # used, reserved, input-only or strapping


def test_board_facts_come_from_the_library():
    board = LIB.get("esp32_devkitc")
    lib = lib_with("esp32_devkitc", reserved_pins=[*board.reserved_pins, "GPIO25"])
    assert codes(spec_with(), lib) == {"reserved_pin"}
    source = Path(module.__file__).read_text()
    assert not re.search(r"GPIO\d|3V3|\b5V\b", source)


# ---------------------------------------------------------------- one test per other code


def test_invalid_spec_when_the_model_was_mutated():
    spec = spec_with()
    spec.parts[0].ref = "Env 1"  # no validate_assignment: an agent could do this
    result = validate_spec(spec, LIB)
    assert {e.code for e in result.errors} == {"invalid_spec"}
    assert result.errors[0].field == "parts[0].ref"


def test_unknown_part_for_a_board_that_isnt_a_board():
    spec = spec_with(lambda d: d["mcu"].update(part_id="bme280_breakout"))
    (error,) = validate_spec(spec, LIB).errors
    assert error.code == "unknown_part" and "esp32_devkitc" in error.message


def test_duplicate_ref():
    spec = spec_with(lambda d: d["parts"].append(dict(d["parts"][3])))
    assert codes(spec) == {"duplicate_ref"}


@pytest.mark.parametrize("ref", ["led1", "esp32"])
def test_unknown_ref(ref):
    def change(d):
        d["connections"].append(
            {"part_ref": ref, "part_pin": "SIG", "mcu_pin": "GPIO4", "bus": "gpio"}
        )

    assert codes(spec_with(change)) == {"unknown_ref"}


def test_unknown_pin_on_the_board():
    spec = spec_with(lambda d: conn(d, "buzzer1", "SIG").update(mcu_pin="GPIO99"))
    (error,) = validate_spec(spec, LIB).errors
    assert error.code == "unknown_pin" and "free output pins: GPIO4" in error.message


def test_unknown_pin_on_the_part():
    spec = spec_with(lambda d: conn(d, "buzzer1", "SIG").update(part_pin="OUT"))
    errors = validate_spec(spec, LIB).errors
    assert {e.code for e in errors} == {"unknown_pin", "unconnected_pin"}
    assert "SIG" in errors[0].message


def test_pin_conflict_for_one_part_pin_on_two_board_pins():
    def change(d):
        d["connections"].append(
            {
                "part_ref": "buzzer1",
                "part_pin": "SIG",
                "mcu_pin": "GPIO4",
                "bus": "gpio",
            }
        )

    assert codes(spec_with(change)) == {"pin_conflict"}


def test_strapping_pin_is_a_warning():
    spec = spec_with(lambda d: conn(d, "buzzer1", "SIG").update(mcu_pin="GPIO2"))
    result = validate_spec(spec, LIB)
    assert result.ok
    (warning,) = result.errors
    assert (warning.code, warning.severity) == ("strapping_pin", "warning")
    assert "GPIO2" in warning.message and "buzzer1.SIG" in warning.message


def test_adc2_pin_only_fails_with_wifi():
    def change(d, wifi):
        conn(d, "soil1", "AOUT").update(mcu_pin="GPIO4")
        d["firmware"]["needs_wifi"] = wifi

    assert codes(spec_with(lambda d: change(d, False))) == set()
    spec = spec_with(lambda d: change(d, True))
    (error,) = validate_spec(spec, LIB).errors
    assert error.code == "adc2_wifi"
    assert error.message.split("free analog pins: ")[1].startswith("GPIO32")


def test_not_adc_pin():
    spec = spec_with(lambda d: conn(d, "soil1", "AOUT").update(mcu_pin="GPIO23"))
    assert codes(spec) == {"not_adc_pin"}


@pytest.mark.parametrize(
    ("ref", "pin", "mcu_pin", "fix"),
    [("env1", "GND", "GPIO4", "GND"), ("buzzer1", "SIG", "3V3", "free output pins")],
)
def test_pin_type_mismatch(ref, pin, mcu_pin, fix):
    spec = spec_with(lambda d: conn(d, ref, pin).update(mcu_pin=mcu_pin))
    (error,) = validate_spec(spec, LIB).errors
    assert error.code == "pin_type_mismatch" and fix in error.message


def test_voltage_mismatch_for_5v_logic_on_a_3v3_pin():
    lib = lib_with("buzzer_passive", logic_voltage=5.0)
    (error,) = validate_spec(spec_with(), lib).errors
    assert error.code == "voltage_mismatch" and "buzzer1.SIG" in error.message


@pytest.mark.parametrize(
    ("ref", "address", "mention"),
    [
        ("env1", "0x3C", "0x76, 0x77"),  # not one of the part's addresses
        (
            "env1",
            "0x77",
            "env1.SDO",
        ),  # SDO not wired to 3V3, so the module answers on 0x76
        ("soil1", "0x40", "isn't an I2C part"),
    ],
)
def test_i2c_address_invalid(ref, address, mention):
    def change(d):
        next(p for p in d["parts"] if p["ref"] == ref)["i2c_address"] = address

    (error,) = validate_spec(spec_with(change), LIB).errors
    assert error.code == "i2c_address_invalid" and mention in error.message


def test_i2c_address_conflict_suggests_the_free_alternative():
    def change(d):
        env2 = dict(d["parts"][0], ref="env2")
        d["parts"].append(env2)
        d["connections"] += [
            dict(c, part_ref="env2")
            for c in d["connections"]
            if c["part_ref"] == "env1"
        ]

    (error,) = validate_spec(spec_with(change), LIB).errors
    assert error.code == "i2c_address_conflict"
    assert "set env2.i2c_address to 0x77 and wire env2.SDO to 3V3" in error.message


def test_power_budget():
    lib = lib_with("esp32_devkitc", power_budget_ma=30)
    (error,) = validate_spec(spec_with(), lib).errors
    assert error.code == "power_budget" and "oled1 20 mA" in error.message
