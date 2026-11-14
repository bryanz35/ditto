"""cross_checks is green on the plant-monitor run and catches each mismatch injected into a copy of it."""

import json
import shutil
from pathlib import Path

import pytest

from backend.contracts.hardware import load_hardware
from backend.contracts.parts import load_library
from backend.contracts.spec import ProjectSpec
from backend.runtime.runs import RunEngine
from backend.runtime.stages import PIPELINE, run_stages
from backend.tools.cross_checks import cross_checks
from backend.tools.toolbox import real_toolbox

RUN = Path(__file__).resolve().parents[3] / "fixtures" / "runs" / "plant_monitor"


@pytest.fixture(scope="module")
def lib():
    return load_library()


@pytest.fixture
def run(tmp_path) -> Path:
    return Path(shutil.copytree(RUN, tmp_path / "run"))


def spec_of(run: Path) -> ProjectSpec:
    return ProjectSpec.model_validate_json((run / "spec.json").read_text())


def edit_json(path: Path, change) -> None:
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data))


def codes(run: Path, lib, spec: ProjectSpec | None = None) -> set[str]:
    result = cross_checks(run, spec or spec_of(run), lib)
    assert result.ok == (not result.errors)
    assert all(e.hint and e.message for e in result.errors)
    return {e.code for e in result.errors}


def test_fixture_run_is_green(lib):
    assert codes(RUN, lib) == set()


def test_pins_h_disagreeing_with_connections(run, lib):
    pins = run / "firmware/include/pins.h"
    pins.write_text(
        pins.read_text().replace("PIN_BUZZER1_SIG 25", "PIN_BUZZER1_SIG 26")
    )
    assert codes(run, lib) == {"pins_mismatch"}


def test_feature_without_cutout(run, lib):
    edit_json(run / "cad/manifest.json", lambda d: d["cutouts"].pop(0))
    assert codes(run, lib) == {"cutout_mismatch"}


def test_placement_outside_cavity(run, lib):
    edit_json(run / "cad/layout.json", lambda d: d["placements"][0].update(x_mm=500.0))
    assert "layout_mismatch" in codes(run, lib)


def test_bom_line_for_part_not_in_spec(run, lib):
    def add_line(d):
        d["lines"].append(
            {**d["lines"][0], "part_id": "sg90_servo", "refs": ["servo1"]}
        )

    edit_json(run / "bom.json", add_line)
    assert "bom_mismatch" in codes(run, lib)


def test_wiring_row_missing(run, lib):
    edit_json(run / "wiring.json", lambda d: d["rows"].pop())
    assert codes(run, lib) == {"wiring_mismatch"}


def test_artifact_from_older_rev_is_stale(run, lib):
    spec = spec_of(run)
    newer = spec.model_copy(update={"rev": spec.rev + 1})
    result = cross_checks(run, newer, lib)
    assert {e.code for e in result.errors} == {"stale_artifact"}
    # one row per stale file: their content isn't also reported as mismatching
    assert len(result.errors) == len(
        json.loads((run / "manifest.json").read_text())["artifacts"]
    )


def test_stale_without_run_manifest(run, lib):
    """Runs made by calling run_stages directly have no manifest.json; artifacts' own spec_rev counts."""
    (run / "manifest.json").unlink()
    edit_json(run / "bom.json", lambda d: d.update(spec_rev=1))
    assert codes(run, lib) == {"stale_artifact"}


def test_listed_artifact_missing(run, lib):
    (run / "cad/base.stl").unlink()
    assert codes(run, lib) == {"missing_artifact"}


def test_unparseable_artifact_is_reported_not_raised(run, lib):
    (run / "wiring.json").write_text("{not json")
    assert codes(run, lib) == {"wiring_mismatch"}


@pytest.mark.slow
def test_green_on_a_real_plant_monitor_run(tmp_path, monkeypatch, lib):
    """Every stage with the real tools (simulate skips without a Wokwi token), then the checks."""
    monkeypatch.setenv("P2D_RUNS_DIR", str(tmp_path))
    spec = spec_of(RUN)
    run = tmp_path / "real"
    (run / "firmware/src").mkdir(parents=True)
    (run / "spec.json").write_text(spec.model_dump_json(indent=2))
    shutil.copy(RUN / "firmware/src/main.cpp", run / "firmware/src/main.cpp")
    engine = RunEngine(None, run_stages)  # type: ignore[arg-type]
    emit = engine.emitter("real")  # writes events.jsonl and manifest.json
    stages: list = PIPELINE
    hw = load_hardware()
    box = real_toolbox()
    results = run_stages("real", stages, spec, emit, toolbox=box, lib=lib, hardware=hw)
    failed = {s: r.errors for s, r in results.items() if not (r.ok or r.skipped)}
    assert failed == {}
    checked = ("manifest.json", "firmware/include/pins.h", "cad/layout.json")
    checked += ("cad/manifest.json", "bom.json", "wiring.json")
    assert all((run / rel).is_file() for rel in checked)
    assert results["checks"].ok, results["checks"].errors
