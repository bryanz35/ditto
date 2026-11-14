"""Deterministic part layout (T11). Stub until T11 merges."""

from pathlib import Path

from backend.contracts.parts import PartLibrary
from backend.contracts.results import ToolResult, not_implemented
from backend.contracts.spec import ProjectSpec


def compute_layout(spec: ProjectSpec, lib: PartLibrary, out_dir: Path) -> ToolResult:
    return not_implemented("compute_layout", "T11")
