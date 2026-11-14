"""Firmware project generation, lint and compile (T12). Stubs until T12 merges."""

from pathlib import Path

from backend.contracts.parts import PartLibrary
from backend.contracts.results import ToolResult, not_implemented
from backend.contracts.spec import ProjectSpec


def write_firmware_project(
    spec: ProjectSpec, lib: PartLibrary, main_cpp: str, out_dir: Path
) -> ToolResult:
    return not_implemented("write_firmware_project", "T12")


def lint_firmware(project_dir: Path) -> ToolResult:
    return not_implemented("lint_firmware", "T12")


def compile_firmware(project_dir: Path) -> ToolResult:
    return not_implemented("compile_firmware", "T12")
