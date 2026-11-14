"""Wokwi diagram generation and simulator run (T26). Stubs until T26 merges."""

from pathlib import Path

from backend.contracts.parts import PartLibrary
from backend.contracts.results import ToolResult, not_implemented
from backend.contracts.spec import ProjectSpec


def build_simulation(
    spec: ProjectSpec, lib: PartLibrary, project_dir: Path, out_dir: Path
) -> ToolResult:
    return not_implemented("build_simulation", "T26")


def run_simulation(
    sim_dir: Path, timeout_ms: int, expect_text: str = "P2D_READY"
) -> ToolResult:
    return not_implemented("run_simulation", "T26")
