"""Cross-domain checks over a run directory (T21). Stub until T21 merges."""

from pathlib import Path

from backend.contracts.parts import PartLibrary
from backend.contracts.results import ToolResult, not_implemented
from backend.contracts.spec import ProjectSpec


def cross_checks(run_dir: Path, spec: ProjectSpec, lib: PartLibrary) -> ToolResult:
    return not_implemented("cross_checks", "T21")
