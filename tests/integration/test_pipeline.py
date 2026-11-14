"""The plant monitor through real_toolbox(), one tool at a time, then the whole chain.

Each step takes fixture inputs (spec, cad/layout.json, main.cpp) or outputs of its own task. Every
tool has merged, so nothing here is xfail: a marker would hide a real failure.
"""

import json
import re
import shutil
from pathlib import Path

import httpx
import pytest
import respx

from backend.contracts.artifacts import Bom, EnclosureManifest, Wiring
from backend.contracts.events import Event
from backend.contracts.parts import load_library
from backend.contracts.runner import run_dir_for
from backend.contracts.spec import Layout, ProjectSpec
from backend.tools.toolbox import real_toolbox
from tests.integration import invariants as inv

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
RUN = FIXTURES / "runs" / "plant_monitor"
INVALID = sorted((FIXTURES / "specs" / "invalid").glob("*.json"))


@pytest.fixture(scope="module")
def tools():
    return real_toolbox()


@pytest.fixture(scope="module")
def lib():
    return load_library()


@pytest.fixture
def spec() -> ProjectSpec:
    return ProjectSpec.model_validate_json(
        (FIXTURES / "specs" / "plant_monitor.json").read_text()
    )


def main_cpp() -> str:
    return (RUN / "firmware" / "src" / "main.cpp").read_text()


def assert_artifacts(
    result, names: set[str], out_dir: Path, ok: bool = True
) -> dict[str, Path]:
    """The tool returned `ok` and wrote the named artifacts inside out_dir."""
    assert result.ok is ok, result.errors
    assert names <= set(result.artifacts), result.artifacts
    paths = {name: Path(result.artifacts[name]) for name in names}
    for name, path in paths.items():
        assert path.is_absolute() and path.is_file(), (name, path)
        assert path.resolve().is_relative_to(out_dir.resolve()), (name, path)
    return paths


# --- validate (T10) --------------------------------------------------------------------------------


def test_validate_plant_monitor(tools, lib, spec):
    result = tools.validate_spec(spec, lib)
    assert result.ok, result.errors
    assert [e for e in result.errors if e.severity == "error"] == []


@pytest.mark.parametrize("path", INVALID, ids=[p.stem for p in INVALID])
def test_validate_invalid_spec_fails_with_its_code(tools, lib, path):
    result = tools.validate_spec(ProjectSpec.model_validate_json(path.read_text()), lib)
    assert not result.ok
    assert {e.code for e in result.errors if e.severity == "error"} == {path.stem}
    assert all(e.message for e in result.errors)


# --- layout and enclosure (T11), assembly (T25) -----------------------------------------------------


def test_compute_layout(tools, lib, spec, tmp_path):
    outputs = []
    for run in ("a", "b"):
        out = tmp_path / run
        result = tools.compute_layout(spec, lib, out)
        path = assert_artifacts(result, {"layout_json"}, out)["layout_json"]
        layout = Layout.model_validate(result.data["layout"])
        assert Layout.model_validate_json(path.read_text()) == layout
        assert inv.check_layout(layout, spec, lib) == []
        outputs.append(path.read_bytes())
    assert outputs[0] == outputs[1], (
        "layout.json differs between two runs of the same spec"
    )


def real_layout(tools, lib, spec, tmp_path: Path) -> Layout:
    """T11's own layout: the T01 fixture layout predates T11's screw posts, so its enclosure tools
    rightly reject it. Written outside the enclosure out_dir."""
    result = tools.compute_layout(spec, lib, tmp_path / "layout")
    assert result.ok, result.errors
    return Layout.model_validate(result.data["layout"])


ENCLOSURE_FILES = {"base_stl", "base_step", "lid_stl", "lid_step", "manifest"}


@pytest.mark.slow
def test_build_enclosure(tools, lib, spec, tmp_path):
    layout = real_layout(tools, lib, spec, tmp_path)
    result = tools.build_enclosure(spec, layout, lib, tmp_path)
    paths = assert_artifacts(result, ENCLOSURE_FILES, tmp_path)
    manifest = EnclosureManifest.model_validate_json(paths["manifest"].read_text())
    assert manifest.spec_rev == spec.rev
    assert manifest.cavity_mm == layout.cavity_mm
    assert inv.check_cutouts(manifest, spec, lib) == []


@pytest.mark.slow
def test_check_enclosure_generic_printer(tools, lib, spec, tmp_path):
    layout = real_layout(tools, lib, spec, tmp_path)
    assert tools.build_enclosure(spec, layout, lib, tmp_path).ok
    result = tools.check_enclosure(spec, layout, lib, tmp_path, "generic")
    assert result.ok, result.errors
    assert result.data["watertight"] is True
    assert result.data["fits_printer"] is True


@pytest.mark.slow
def test_build_assembly(tools, lib, spec, tmp_path):
    import trimesh

    layout = real_layout(tools, lib, spec, tmp_path)
    assert tools.build_enclosure(spec, layout, lib, tmp_path).ok  # the shells it shows
    result = tools.build_assembly(spec, layout, lib, tmp_path)
    path = assert_artifacts(result, {"assembly_glb"}, tmp_path)["assembly_glb"]
    scene = trimesh.load(path)
    names = set(scene.graph.nodes) | set(scene.geometry)
    missing = {p.ref for p in layout.placements} - names
    assert not missing, f"no node for {missing} in {sorted(names)}"


# --- firmware (T12) --------------------------------------------------------------------------------


def test_write_firmware_project_and_lint(tools, lib, spec, tmp_path):
    result = tools.write_firmware_project(spec, lib, main_cpp(), tmp_path)
    paths = assert_artifacts(result, {"platformio_ini", "pins_h", "main_cpp"}, tmp_path)
    assert inv.check_pins(paths["pins_h"].read_text(), spec) == []
    ini = paths["platformio_ini"].read_text()
    board = lib.get(spec.mcu.part_id)
    assert re.search(
        rf"^board\s*=\s*{re.escape(board.pio_board)}\s*$", ini, re.MULTILINE
    ), ini
    for p in [spec.mcu, *spec.parts]:
        for dep in lib.get(p.part_id).pio_lib_deps:
            assert dep in ini, f"{dep} ({p.ref}) missing from platformio.ini"
    lint = tools.lint_firmware(tmp_path)
    assert lint.ok, lint.errors


@pytest.mark.slow
def test_compile_firmware(tools, lib, spec, tmp_path):
    assert tools.write_firmware_project(spec, lib, main_cpp(), tmp_path).ok
    result = tools.compile_firmware(tmp_path)
    assert result.ok, (result.errors, result.log)


# --- wiring (T14), simulation (T26), BOM (T16) -----------------------------------------------------


def test_build_wiring(tools, lib, spec, tmp_path):
    result = tools.build_wiring(spec, lib, tmp_path)
    path = assert_artifacts(result, {"wiring_json"}, tmp_path)["wiring_json"]
    wiring = Wiring.model_validate_json(path.read_text())
    assert Wiring.model_validate(result.data) == wiring
    assert inv.check_wiring(wiring, spec, lib) == []


def test_build_simulation(tools, lib, spec, tmp_path):
    project = Path(shutil.copytree(RUN / "firmware", tmp_path / "firmware"))
    out = tmp_path / "sim"
    result = tools.build_simulation(spec, lib, project, out)
    paths = assert_artifacts(result, {"diagram_json", "wokwi_toml"}, out)
    diagram = json.loads(paths["diagram_json"].read_text())
    types = {part["id"]: part["type"] for part in diagram["parts"]}
    expected = {
        p.ref: lib.get(p.part_id).wokwi_type
        for p in spec.parts
        if lib.get(p.part_id).wokwi_type
    }
    assert expected.items() <= types.items(), types
    if board_type := lib.get(spec.mcu.part_id).wokwi_board:
        assert types.get(spec.mcu.ref) == board_type, types


@pytest.fixture
def no_network():
    """Every HTTP call fails, so price_bom must fall back to the cache or manual prices."""
    with respx.mock(assert_all_called=False) as mock:
        mock.route().mock(side_effect=httpx.ConnectError("network disabled in tests"))
        yield


def price(tools, lib, spec, out: Path, ok: bool = True) -> Bom:
    """ok=False: over budget is a failed check, but the BOM is still written."""
    result = tools.price_bom(spec, lib, None, out)
    path = assert_artifacts(result, {"bom_json"}, out, ok)["bom_json"]
    bom = Bom.model_validate_json(path.read_text())
    assert Bom.model_validate(result.data) == bom
    assert inv.check_bom(bom, spec, lib) == []
    return bom


def test_price_bom(tools, lib, spec, tmp_path, no_network):
    bom = price(tools, lib, spec, tmp_path)
    assert all(line.unit_price_usd is not None for line in bom.lines), bom.lines


def test_price_bom_owned_part_is_free(tools, lib, spec, tmp_path, no_network):
    spec.user.owned = {"bme280_breakout": 1}
    bom = price(tools, lib, spec, tmp_path)
    line = next(line for line in bom.lines if line.part_id == "bme280_breakout")
    assert (line.owned_qty, line.line_total_usd) == (1, 0.0)


def test_price_bom_budget_boundary(tools, lib, spec, tmp_path, no_network):
    total = price(tools, lib, spec, tmp_path / "a").total_usd
    spec.user.budget_usd = total
    assert price(tools, lib, spec, tmp_path / "b").over_budget is False
    spec.user.budget_usd = total - 0.01
    assert price(tools, lib, spec, tmp_path / "c", ok=False).over_budget is True


# --- cross-checks (T21) and the whole chain through run_stages --------------------------------------------------


def test_cross_checks_accept_fixture_run(tools, lib, spec, tmp_path):
    run = Path(shutil.copytree(RUN, tmp_path / "run"))
    result = tools.cross_checks(run, spec, lib)
    assert result.ok, result.errors


@pytest.mark.slow
def test_full_chain_through_run_stages(
    tools, lib, spec, tmp_path, monkeypatch, no_network
):
    from backend.runtime.stages import run_stages

    monkeypatch.setenv("P2D_RUNS_DIR", str(tmp_path))
    run_dir = run_dir_for("chain")
    (run_dir / "firmware" / "src").mkdir(parents=True)
    (run_dir / "spec.json").write_text(spec.model_dump_json(indent=2))
    (run_dir / "firmware" / "src" / "main.cpp").write_text(main_cpp())
    events: list[Event] = []

    results = run_stages(
        "chain", list(inv.PIPELINE), spec, events.append, toolbox=tools, lib=lib
    )

    assert set(results) == set(inv.PIPELINE)
    bad = {
        stage: r.errors
        for stage, r in results.items()
        if not (r.ok or (stage == "simulate" and r.skipped))
    }
    assert not bad, bad
    for e in events:
        assert e.spec_rev == spec.rev, e
        for rel in e.artifacts.values():
            assert not Path(rel).is_absolute() and (run_dir / rel).is_file(), (
                e.stage,
                rel,
            )
    final = inv.final_statuses(events)
    assert {s: final.get(s) for s in inv.PIPELINE if final.get(s) != "passed"} in (
        {},
        {"simulate": "skipped"},
    )
    assert inv.check_run_dir(run_dir, lib, engine=False) == []
    checks = tools.cross_checks(run_dir, spec, lib)
    assert checks.ok, checks.errors
