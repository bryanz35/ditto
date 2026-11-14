"""run_stages: the StageRunner (backend/contracts/runner.py), the only code that executes stages
(T14). Stub until T14 merges. The engine binds toolbox and lib, e.g. with functools.partial."""

from backend.contracts.events import Stage
from backend.contracts.parts import PartLibrary
from backend.contracts.results import ToolResult, not_implemented
from backend.contracts.runner import Emit
from backend.contracts.spec import ProjectSpec
from backend.contracts.tools import ToolBox


def run_stages(
    run_id: str,
    stages: list[Stage],
    spec: ProjectSpec,
    emit: Emit,
    *,
    toolbox: ToolBox,
    lib: PartLibrary,
) -> dict[str, ToolResult]:
    return {stage: not_implemented(f"run_stages({stage})", "T14") for stage in stages}
