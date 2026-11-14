"""fake_toolbox(): every tool succeeds by copying the plant-monitor fixture run into its out_dir.
For agent tests and frontend work without a model, compiler, CAD kernel or API keys."""

import json
import shutil
from pathlib import Path

from backend.contracts.parts import PartLibrary
from backend.contracts.results import ToolResult
from backend.contracts.spec import Layout, ProjectSpec
from backend.contracts.tools import ToolBox

FIXTURE_RUN = (
    Path(__file__).resolve().parents[2] / "fixtures" / "runs" / "plant_monitor"
)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def _copy(subdir: str, out_dir: Path, files: dict[str, str]) -> dict[str, str]:
    artifacts = {}
    for name, rel in files.items():
        dest = Path(out_dir) / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FIXTURE_RUN / subdir / rel, dest)
        artifacts[name] = str(dest)
    return artifacts


def _json(rel: str) -> dict:
    return json.loads((FIXTURE_RUN / rel).read_text())


def validate_spec(spec: ProjectSpec, lib: PartLibrary) -> ToolResult:
    return ToolResult(ok=True)


def compute_layout(spec: ProjectSpec, lib: PartLibrary, out_dir: Path) -> ToolResult:
    artifacts = _copy("cad", out_dir, {"layout_json": "layout.json"})
    return ToolResult(
        ok=True, artifacts=artifacts, data={"layout": _json("cad/layout.json")}
    )


def build_enclosure(
    spec: ProjectSpec, layout: Layout, lib: PartLibrary, out_dir: Path
) -> ToolResult:
    files = {
        "base_stl": "base.stl",
        "base_step": "base.step",
        "lid_stl": "lid.stl",
        "lid_step": "lid.step",
        "manifest": "manifest.json",
    }
    return ToolResult(ok=True, artifacts=_copy("cad", out_dir, files))


def check_enclosure(
    spec: ProjectSpec, layout: Layout, lib: PartLibrary, out_dir: Path, printer_id: str
) -> ToolResult:
    return ToolResult(ok=True, data={"watertight": True, "fits_printer": True})


def build_assembly(
    spec: ProjectSpec, layout: Layout, lib: PartLibrary, out_dir: Path
) -> ToolResult:
    return ToolResult(
        ok=True, artifacts=_copy("cad", out_dir, {"assembly_glb": "assembly.glb"})
    )


def write_firmware_project(
    spec: ProjectSpec, lib: PartLibrary, main_cpp: str, out_dir: Path
) -> ToolResult:
    files = {"platformio_ini": "platformio.ini", "pins_h": "include/pins.h"}
    artifacts = _copy("firmware", out_dir, files)
    main = Path(out_dir) / "src" / "main.cpp"
    main.parent.mkdir(parents=True, exist_ok=True)
    main.write_text(main_cpp)
    return ToolResult(ok=True, artifacts={**artifacts, "main_cpp": str(main)})


def lint_firmware(project_dir: Path) -> ToolResult:
    return ToolResult(ok=True)


def compile_firmware(project_dir: Path) -> ToolResult:
    return ToolResult(ok=True, log="fake compile: [SUCCESS]")


def build_wiring(spec: ProjectSpec, lib: PartLibrary, out_dir: Path) -> ToolResult:
    artifacts = _copy(".", out_dir, {"wiring_json": "wiring.json"})
    return ToolResult(ok=True, artifacts=artifacts, data=_json("wiring.json"))


def build_simulation(
    spec: ProjectSpec, lib: PartLibrary, project_dir: Path, out_dir: Path
) -> ToolResult:
    files = {"diagram_json": "diagram.json", "wokwi_toml": "wokwi.toml"}
    return ToolResult(ok=True, artifacts=_copy("sim", out_dir, files))


def run_simulation(
    sim_dir: Path, timeout_ms: int, expect_text: str = "P2D_READY"
) -> ToolResult:
    return ToolResult(
        ok=True, artifacts=_copy("sim", sim_dir, {"serial_log": "serial.log"})
    )


def price_bom(
    spec: ProjectSpec,
    lib: PartLibrary,
    prices: Path | None,
    owned: dict[str, int],
    out_dir: Path,
) -> ToolResult:
    artifacts = _copy(".", out_dir, {"bom_json": "bom.json"})
    return ToolResult(ok=True, artifacts=artifacts, data=_json("bom.json"))


def cross_checks(run_dir: Path, spec: ProjectSpec, lib: PartLibrary) -> ToolResult:
    return ToolResult(ok=True)


def preprocess_input(paths: list[Path], out_dir: Path) -> ToolResult:
    images = [str(p) for p in paths if Path(p).suffix.lower() in IMAGE_SUFFIXES]
    return ToolResult(ok=True, data={"images": images, "transcript": None})


def fake_toolbox() -> ToolBox:
    return ToolBox(
        validate_spec=validate_spec,
        compute_layout=compute_layout,
        build_enclosure=build_enclosure,
        check_enclosure=check_enclosure,
        build_assembly=build_assembly,
        write_firmware_project=write_firmware_project,
        lint_firmware=lint_firmware,
        compile_firmware=compile_firmware,
        build_wiring=build_wiring,
        build_simulation=build_simulation,
        run_simulation=run_simulation,
        price_bom=price_bom,
        cross_checks=cross_checks,
        preprocess_input=preprocess_input,
    )
