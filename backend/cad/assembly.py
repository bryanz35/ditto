"""Assembly preview, assembly.glb (T25). Stub until T25 merges."""

from pathlib import Path

from backend.contracts.parts import PartLibrary
from backend.contracts.results import ToolResult, not_implemented
from backend.contracts.spec import Layout, ProjectSpec


def build_assembly(
    spec: ProjectSpec, layout: Layout, lib: PartLibrary, out_dir: Path
) -> ToolResult:
    return not_implemented("build_assembly", "T25")
