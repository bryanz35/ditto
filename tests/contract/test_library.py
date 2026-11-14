import pytest

from backend.contracts.parts import PARTS_DIR, BoardDef, load_library

PLANT_MONITOR_PARTS = {
    "esp32_devkitc",
    "bme280_breakout",
    "ssd1306_096_i2c",
    "soil_moisture_capacitive",
    "buzzer_passive",
}


def test_library_loads_the_plant_monitor_parts():
    lib = load_library()
    assert PLANT_MONITOR_PARTS <= set(lib.parts)
    assert isinstance(lib.get("esp32_devkitc"), BoardDef)


def test_every_part_cites_a_source_and_its_snippet_exists():
    for part in load_library().parts.values():
        assert part.source, part.id
        if part.snippet:
            assert (PARTS_DIR / part.snippet).is_file(), part.snippet


def test_pin_type():
    lib = load_library()
    assert lib.pin_type("buzzer_passive", "SIG") == "gpio_out"
    assert lib.pin_type("buzzer_passive", "NOPE") is None
    assert lib.pin_type("no_such_part", "SIG") is None


def test_load_library_rejects_a_file_whose_id_differs(tmp_path):
    src = (PARTS_DIR / "library" / "buzzer_passive.yaml").read_text()
    (tmp_path / "other_name.yaml").write_text(src)
    with pytest.raises(ValueError, match="doesn't match the file name"):
        load_library(tmp_path)


def test_load_library_rejects_unknown_pin_types(tmp_path):
    src = (PARTS_DIR / "library" / "buzzer_passive.yaml").read_text()
    (tmp_path / "buzzer_passive.yaml").write_text(
        src.replace("type: gpio_out", "type: pwm")
    )
    with pytest.raises(ValueError, match="buzzer_passive.yaml"):
        load_library(tmp_path)
