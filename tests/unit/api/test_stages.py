from dataclasses import replace
from pathlib import Path

import pytest

from backend.contracts.parts import load_library
from backend.contracts.results import not_implemented
from backend.contracts.spec import ProjectSpec
from backend.runtime.stages import PIPELINE, run_stages
from backend.tools.fakes import fake_toolbox
from tests.unit.api.conftest import MODE_V

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"
SPEC = ProjectSpec.model_validate_json(
    (FIXTURES / "specs" / "plant_monitor.json").read_text()
)
MAIN_CPP = (
    FIXTURES / "runs" / "plant_monitor" / "firmware" / "src" / "main.cpp"
).read_text()


@pytest.fixture
def run(runs_dir):
    main = runs_dir / "r1" / "firmware" / "src" / "main.cpp"
    main.parent.mkdir(parents=True)
    main.write_text(MAIN_CPP)

    def go(toolbox=None, hardware=MODE_V):
        events = []
        results = run_stages(
            "r1",
            PIPELINE,
            SPEC,
            events.append,
            toolbox=toolbox or fake_toolbox(),
            lib=load_library(),
            hardware=hardware,
        )
        final = {e.stage: e for e in events if e.status != "running"}
        assert list(final) == PIPELINE == list(results)  # every stage finished
        return final

    return go


def test_all_stages_pass_with_relative_artifacts(run):
    final = run()
    assert {e.status for e in final.values()} == {"passed"}
    assert final["enclosure"].artifacts["base_stl"] == "cad/base.stl"
    assert final["firmware"].artifacts["main_cpp"] == "firmware/src/main.cpp"
    assert final["validate"].artifacts == {"spec": "spec.json"}


def test_mode_p_skips_simulate(run):
    final = run(hardware=MODE_V.model_copy(update={"mode": "P", "simulate": False}))
    assert final["simulate"].status == "skipped"
    assert "mode P" in final["simulate"].message


def test_not_implemented_tools_and_their_dependents_are_skipped(run):
    stubbed = replace(
        fake_toolbox(),
        compute_layout=lambda *a: not_implemented("compute_layout", "T11"),
        compile_firmware=lambda *a: not_implemented("compile_firmware", "T12"),
    )
    final = run(stubbed)
    for stage in ("layout", "enclosure", "assembly", "firmware", "simulate"):
        assert final[stage].status == "skipped", stage
    assert final["wiring"].status == final["bom"].status == "passed"


def test_a_crashing_tool_fails_its_stage_only(run):
    def boom(*a):
        raise RuntimeError("kaboom")

    final = run(replace(fake_toolbox(), price_bom=boom))
    assert final["bom"].status == "failed"
    assert (
        final["bom"].errors[0].code == "exception" and "kaboom" in final["bom"].message
    )
    assert final["checks"].status == "passed"
