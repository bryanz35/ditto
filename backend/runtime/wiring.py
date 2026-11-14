"""wiring.json for the wiring tab (T14). Stub until T14 merges."""

from pathlib import Path

from backend.contracts.parts import PartLibrary
from backend.contracts.results import ToolResult, not_implemented
from backend.contracts.spec import ProjectSpec


def build_wiring(spec: ProjectSpec, lib: PartLibrary, out_dir: Path) -> ToolResult:
    return not_implemented("build_wiring", "T14")
