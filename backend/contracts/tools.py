"""Signatures of every tool, and the ToolBox that bundles them so the agent and the API can swap
stubs, fakes (backend/tools/fakes.py) and real tools (backend/tools/toolbox.py).

Every tool returns a ToolResult and writes files only inside the directory it's given, returning
them in `artifacts`. Comments list the artifact names (and data keys) each tool returns.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from backend.contracts.parts import PartLibrary
from backend.contracts.results import ToolResult
from backend.contracts.spec import Layout, ProjectSpec


class ValidateSpec(Protocol):  # T10
    def __call__(self, spec: ProjectSpec, lib: PartLibrary) -> ToolResult: ...


class ComputeLayout(Protocol):  # T11. artifacts: layout_json. data: layout (Layout)
    def __call__(
        self, spec: ProjectSpec, lib: PartLibrary, out_dir: Path
    ) -> ToolResult: ...


class BuildEnclosure(Protocol):
    """T11. artifacts: base_stl, base_step, lid_stl, lid_step, manifest"""

    def __call__(
        self, spec: ProjectSpec, layout: Layout, lib: PartLibrary, out_dir: Path
    ) -> ToolResult: ...


class CheckEnclosure(Protocol):
    """T11. Reads build_enclosure's STLs. data: watertight, fits_printer"""

    def __call__(
        self,
        spec: ProjectSpec,
        layout: Layout,
        lib: PartLibrary,
        out_dir: Path,
        printer_id: str,
    ) -> ToolResult: ...


class BuildAssembly(Protocol):  # T25. artifacts: assembly_glb
    def __call__(
        self, spec: ProjectSpec, layout: Layout, lib: PartLibrary, out_dir: Path
    ) -> ToolResult: ...


class WriteFirmwareProject(Protocol):
    """T12. artifacts: platformio_ini, pins_h, main_cpp"""

    def __call__(
        self, spec: ProjectSpec, lib: PartLibrary, main_cpp: str, out_dir: Path
    ) -> ToolResult: ...


class LintFirmware(Protocol):  # T12
    def __call__(self, project_dir: Path) -> ToolResult: ...


class CompileFirmware(Protocol):  # T12. log: last 40 lines of the build
    def __call__(self, project_dir: Path) -> ToolResult: ...


class BuildWiring(Protocol):  # T14. artifacts: wiring_json. data: Wiring
    def __call__(
        self, spec: ProjectSpec, lib: PartLibrary, out_dir: Path
    ) -> ToolResult: ...


class BuildSimulation(Protocol):  # T26. artifacts: diagram_json, wokwi_toml
    def __call__(
        self, spec: ProjectSpec, lib: PartLibrary, project_dir: Path, out_dir: Path
    ) -> ToolResult: ...


class RunSimulation(Protocol):  # T26. artifacts: serial_log, screenshot
    def __call__(
        self, sim_dir: Path, timeout_ms: int, expect_text: str
    ) -> ToolResult: ...


class PriceBom(Protocol):  # T16. artifacts: bom_json. data: Bom
    def __call__(
        self, spec: ProjectSpec, lib: PartLibrary, prices: Path | None, out_dir: Path
    ) -> ToolResult:
        """prices: price cache file (None = backend/parts/prices.json). Owned quantities come
        from spec.user.owned, so a rerun from the spec alone prices the same."""
        ...


class CrossChecks(Protocol):  # T21. Reads the run directory's artifacts
    def __call__(
        self, run_dir: Path, spec: ProjectSpec, lib: PartLibrary
    ) -> ToolResult: ...


class PreprocessInput(Protocol):
    """T17. data: images (list of paths), transcript (str | None)"""

    def __call__(self, paths: list[Path], out_dir: Path) -> ToolResult: ...


@dataclass(frozen=True)
class ToolBox:
    validate_spec: ValidateSpec
    compute_layout: ComputeLayout
    build_enclosure: BuildEnclosure
    check_enclosure: CheckEnclosure
    build_assembly: BuildAssembly
    write_firmware_project: WriteFirmwareProject
    lint_firmware: LintFirmware
    compile_firmware: CompileFirmware
    build_wiring: BuildWiring
    build_simulation: BuildSimulation
    run_simulation: RunSimulation
    price_bom: PriceBom
    cross_checks: CrossChecks
    preprocess_input: PreprocessInput
