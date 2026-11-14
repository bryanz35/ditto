"""Enclosure build from the box_lid template (T11). Stub until T11 merges."""

from pathlib import Path

from backend.contracts.parts import PartLibrary
from backend.contracts.results import ToolResult, not_implemented
from backend.contracts.spec import Layout, ProjectSpec


def build_enclosure(
    spec: ProjectSpec, layout: Layout, lib: PartLibrary, out_dir: Path
) -> ToolResult:
    return not_implemented("build_enclosure", "T11")
