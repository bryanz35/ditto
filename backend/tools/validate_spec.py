"""Spec validator (T10). Stub until T10 merges."""

from backend.contracts.parts import PartLibrary
from backend.contracts.results import ToolResult, not_implemented
from backend.contracts.spec import ProjectSpec


def validate_spec(spec: ProjectSpec, lib: PartLibrary) -> ToolResult:
    return not_implemented("validate_spec", "T10")
