from itertools import pairwise
from pathlib import Path

import pytest

from backend.contracts.artifacts import Bom, EnclosureManifest, RunManifest, Wiring
from backend.contracts.events import STAGES, Event
from backend.contracts.parts import load_library
from backend.contracts.spec import Layout, ProjectSpec

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
RUN = FIXTURES / "runs" / "plant_monitor"
VALIDATOR_CODES = {
    "pin_conflict",
    "reserved_pin",
    "input_only_output",
    "i2c_address_conflict",
    "voltage_mismatch",
    "unconnected_pin",
    "unknown_part",
}


def load_spec(path: Path) -> ProjectSpec:
    return ProjectSpec.model_validate_json(path.read_text())


def test_plant_monitor_spec_uses_real_library_pins():
    spec = load_spec(FIXTURES / "specs" / "plant_monitor.json")
    lib = load_library()
    part_ids = {p.ref: p.part_id for p in [spec.mcu, *spec.parts]}
    board_pins = {p.name for p in lib.get(spec.mcu.part_id).pins}
    for c in spec.connections:
        assert lib.pin_type(part_ids[c.part_ref], c.part_pin), c
        assert c.mcu_pin in board_pins, c


def test_one_invalid_spec_per_validator_code():
    files = {p.stem: p for p in (FIXTURES / "specs" / "invalid").glob("*.json")}
    assert set(files) == VALIDATOR_CODES
    for path in files.values():
        load_spec(path)  # shape-valid: only the hardware is wrong


def test_event_fixture_is_a_complete_run():
    lines = (FIXTURES / "events" / "plant_monitor.jsonl").read_text().splitlines()
    events = [Event.model_validate_json(line) for line in lines]
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    assert all(a.ts <= b.ts for a, b in pairwise(events))
    assert set(STAGES) <= {e.stage for e in events}
    # one validation failure, then a retry passes
    validate = [e.status for e in events if e.stage == "validate"]
    assert validate.index("failed") < validate.index("passed")
    assert events[-1].stage == "done" and events[-1].status == "passed"
    for e in events:
        for path in e.artifacts.values():
            assert (RUN / path).is_file(), path


@pytest.mark.parametrize(
    ("rel", "model"),
    [
        ("manifest.json", RunManifest),
        ("wiring.json", Wiring),
        ("bom.json", Bom),
        ("cad/layout.json", Layout),
        ("cad/manifest.json", EnclosureManifest),
    ],
)
def test_run_files_match_their_contracts(rel, model):
    model.model_validate_json((RUN / rel).read_text())


def test_run_manifest_points_at_real_files():
    manifest = RunManifest.model_validate_json((RUN / "manifest.json").read_text())
    for info in manifest.artifacts.values():
        assert (RUN / info.path).is_file(), info.path
    assert load_spec(RUN / "spec.json").rev == manifest.spec_rev
