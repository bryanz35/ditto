import json
from pathlib import Path

from backend.contracts.parts import load_library
from backend.contracts.spec import ProjectSpec
from backend.runtime.wiring import build_wiring

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"
SPEC = ProjectSpec.model_validate_json(
    (FIXTURES / "specs" / "plant_monitor.json").read_text()
)


def test_plant_monitor_wiring_matches_the_fixture(tmp_path):
    result = build_wiring(SPEC, load_library(), tmp_path)
    assert result.ok, result.errors
    written = json.loads(Path(result.artifacts["wiring_json"]).read_text())
    expected = json.loads(
        (FIXTURES / "runs" / "plant_monitor" / "wiring.json").read_text()
    )
    assert written == expected == result.data


def test_unknown_pin_names_the_part_and_its_pins(tmp_path):
    spec = SPEC.model_copy(deep=True)
    spec.connections[0].part_pin = "NOPE"
    result = build_wiring(spec, load_library(), tmp_path)
    assert not result.ok and result.errors[0].code == "unknown_pin"
    assert "NOPE" in result.errors[0].message and "SDA" in result.errors[0].message
    assert not (tmp_path / "wiring.json").exists()
