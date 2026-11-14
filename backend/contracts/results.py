"""What every tool returns. Tools never raise for expected failures: they return a ToolResult.

Error codes are owned by each tool and listed in its module docstring (the seven validator codes are
also fixture names in fixtures/specs/invalid/). Consumers never branch on a specific code: retry
logic uses `ok`, `skipped` and `severity`, and the checks panel shows any code with its message.
"""

from typing import Any, Literal

from backend.contracts.base import Model

SKIP_CODES = ("not_implemented", "skipped")
"""Error codes that mean "this stage didn't run" (e.g. no WOKWI_CLI_TOKEN): emit the stage as
skipped, don't retry it, and don't count it as a failure."""


class ToolError(Model):
    code: str
    """Stable snake_case id, e.g. "pin_conflict"."""
    message: str
    """Read by an LLM: name the pin, part and value, and give free alternatives where possible."""
    field: str | None = None
    """Spec path the error is about, e.g. "connections[3].mcu_pin"."""
    hint: str | None = None
    severity: Literal["error", "warning"] = "error"


class ToolResult(Model):
    ok: bool
    errors: list[ToolError] = []
    """Warnings may appear even when ok is true."""
    artifacts: dict[str, str] = {}
    """Artifact name -> absolute path of a file the tool wrote inside its out_dir. (Events carry
    paths relative to the run directory; the StageRunner converts.)"""
    data: dict[str, Any] = {}
    """JSON-serialisable values (models as model_dump(mode="json"))."""
    log: str = ""

    @property
    def skipped(self) -> bool:
        return any(e.code in SKIP_CODES for e in self.errors)


def not_implemented(tool: str, task: str) -> ToolResult:
    """What stub tools return until their task merges."""
    return ToolResult(
        ok=False,
        errors=[
            ToolError(
                code="not_implemented", message=f"{tool} isn't implemented yet ({task})"
            )
        ],
    )
