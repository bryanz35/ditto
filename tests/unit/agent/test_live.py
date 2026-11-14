"""make test-live: the plant-monitor prompt with a real model (P2D_MODEL) and fake tools."""

import json
import os

import pytest

from backend.agent import AgentRunner
from backend.contracts.parts import load_library
from backend.contracts.runner import RunRequest
from backend.contracts.spec import UserContext
from backend.tools.fakes import fake_toolbox
from backend.tools.validate_spec import validate_spec
from tests.unit.agent.conftest import FIXTURE_SPEC, FakeStageRunner

pytestmark = pytest.mark.live


async def test_plant_monitor_spec_passes_validation(events):
    if not (os.environ.get("P2D_MODEL") and os.environ.get("ANTHROPIC_API_KEY")):
        pytest.skip("needs P2D_MODEL and ANTHROPIC_API_KEY in .env")
    prompt = json.loads(FIXTURE_SPEC.read_text())["prompt"]
    runner = AgentRunner(fake_toolbox(), None, FakeStageRunner(), question_timeout_s=1)

    spec = await runner.run(
        RunRequest(run_id="live", prompt=prompt, user=UserContext(budget_usd=30)),
        events.append,
    )

    result = validate_spec(spec, load_library())
    if result.skipped:
        pytest.skip("validate_spec isn't implemented yet (T10)")
    assert result.ok, result.errors
    assert any(e.data.get("todos") for e in events if e.stage == "plan")


async def test_level_changes_explanations(capsys):
    """T37: the same prompt at beginner and expert gives visibly different reasons."""
    if not (os.environ.get("P2D_MODEL") and os.environ.get("ANTHROPIC_API_KEY")):
        pytest.skip("needs P2D_MODEL and ANTHROPIC_API_KEY in .env")
    prompt = json.loads(FIXTURE_SPEC.read_text())["prompt"]
    reasons = {}
    for level in ("beginner", "expert"):
        runner = AgentRunner(
            fake_toolbox(), None, FakeStageRunner(), question_timeout_s=1
        )
        user = UserContext(budget_usd=30, level=level)
        spec = await runner.run(
            RunRequest(run_id=f"live-{level}", prompt=prompt, user=user), lambda e: None
        )
        assert spec.user.level == level
        reasons[level] = [p.reason for p in [spec.mcu, *spec.parts]] + [
            c.reason for c in spec.connections if c.reason
        ]
        with capsys.disabled():
            print(f"\n--- {level} ---", *reasons[level], sep="\n")

    def mean_len(texts: list[str]) -> float:
        return sum(map(len, texts)) / len(texts)

    assert reasons["beginner"] != reasons["expert"]
    assert mean_len(reasons["beginner"]) > mean_len(reasons["expert"])
