"""Printability and fit checks (T11). Stub until T11 merges."""

from pathlib import Path

from backend.contracts.parts import PartLibrary
from backend.contracts.results import ToolResult, not_implemented
from backend.contracts.spec import Layout, ProjectSpec


def check_enclosure(
    spec: ProjectSpec, layout: Layout, lib: PartLibrary, out_dir: Path, printer_id: str
) -> ToolResult:
    return not_implemented("check_enclosure", "T11")
