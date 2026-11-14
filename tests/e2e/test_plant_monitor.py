"""G1 gate: the plant-monitor prompt end to end through the API with a real model and real tools."""

import json
from pathlib import Path

import pytest

from backend.contracts.artifacts import Bom
from backend.contracts.runner import run_dir_for
from backend.contracts.spec import ProjectSpec, UserContext
from tests.e2e.harness import saved_spec, start_run, wait_for_done
from tests.integration import invariants as inv

FIXTURE_SPEC = Path(__file__).resolve().parents[2] / "fixtures/specs/plant_monitor.json"
PROMPT = ProjectSpec.model_validate_json(FIXTURE_SPEC.read_text()).prompt
REQUIRED_ARTIFACTS = {
    "spec",
    "layout_json",
    "base_stl",
    "base_step",
    "lid_stl",
    "lid_step",
    "manifest",
    "platformio_ini",
    "pins_h",
    "main_cpp",
    "wiring_json",
    "bom_json",
}

pytestmark = [
    pytest.mark.slow,
    pytest.mark.live,
    pytest.mark.xfail(
        reason="needs T14 (API and run engine) and T20 (integration)", strict=False
    ),
]


async def test_plant_monitor_end_to_end(api):
    run_id = await start_run(api, PROMPT, UserContext(budget_usd=30.0))
    events = await wait_for_done(run_id)

    assert inv.check_events(events) == []
    assert events[0].seq == 1
    assert inv.failed_stages(events) == []
    run_dir = run_dir_for(run_id)
    assert inv.check_run_dir(run_dir) == []

    spec = saved_spec(run_id)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    missing = REQUIRED_ARTIFACTS - set(manifest["artifacts"])
    assert not missing, f"manifest.json lacks {missing}"
    assert all(e.spec_rev == spec.rev for e in events if e.stage in ("checks", "done"))
    bom = Bom.model_validate_json((run_dir / "bom.json").read_text())
    assert not bom.over_budget, bom.total_usd

    response = await api.get(f"/runs/{run_id}/spec")
    response.raise_for_status()
    assert ProjectSpec.model_validate(response.json()) == spec
