"""BOM pricing with the Nexar API and a JSON cache (T16). Stub until T16 merges."""

from pathlib import Path

from backend.contracts.parts import PartLibrary
from backend.contracts.results import ToolResult, not_implemented
from backend.contracts.spec import ProjectSpec


def price_bom(
    spec: ProjectSpec, lib: PartLibrary, prices: Path | None, out_dir: Path
) -> ToolResult:
    return not_implemented("price_bom", "T16")
