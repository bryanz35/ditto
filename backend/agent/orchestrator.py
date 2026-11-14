"""build_agent(): the deepagents orchestrator with three specialist sub-agents (deepagents 0.7.38).

Each sub-agent sees only its own tools. Planning (write_todos) is opt-in in this version, so the
TodoListMiddleware is added explicitly. The default general-purpose sub-agent is turned off so the
orchestrator can't route around the specialists.
"""

import os
from collections.abc import Callable
from pathlib import Path

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from langchain.agents.middleware import ModelRequest, TodoListMiddleware, dynamic_prompt
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver

from backend.contracts.spec import UserContext

HERE = Path(__file__).resolve().parent
EXAMPLE_SPEC = HERE.parents[1] / "fixtures" / "specs" / "plant_monitor.json"
AGENTS_MD = "/AGENTS.md"
"""Path of the house rules in the agent's in-memory scratchpad (see house_rules())."""

ModelLike = str | BaseChatModel

SUBAGENTS = {
    "parts-and-pins": (
        "parts",
        (
            "Writes and saves the validated project spec: requirements, and for a device with "
            "electronics its library parts and pins (none for a print-only object). Use first, "
            "and for any change to parts or pins."
        ),
        ["search_parts", "write_spec", "request_change"],
    ),
    "firmware": (
        "firmware",
        (
            "Writes Arduino main.cpp for the saved spec and compiles it. Use after the spec is saved "
            "and after any change to parts, pins or behaviours."
        ),
        ["write_firmware", "request_change"],
    ),
    "enclosure": (
        "enclosure",
        (
            "Designs the printed parts and builds and checks them: a plain case for the "
            "electronics, a custom body around it, or a print-only object written as build123d "
            "code. Use after the spec is saved and for any shape, wall or size change."
        ),
        ["set_enclosure", "write_model", "request_change"],
    ),
}
ORCHESTRATOR_TOOLS = ["ask_user", "price_bom"]


def model_spec(model: ModelLike | None = None) -> ModelLike:
    """P2D_MODEL may be "provider:model" or a bare Anthropic model name."""
    model = model or os.environ.get("P2D_MODEL")
    if not model:
        raise RuntimeError("Set P2D_MODEL in .env (e.g. claude-sonnet-5-5)")
    if isinstance(model, str) and ":" not in model:
        return f"anthropic:{model}"
    return model


def prompt(name: str) -> str:
    text = (HERE / "prompts" / f"{name}.md").read_text()
    return text.replace("{example}", EXAMPLE_SPEC.read_text().strip())


def house_rules() -> str:
    return (HERE / "AGENTS.md").read_text()


def profile(user: UserContext | None) -> str:
    """The user's level rules and name, added to every system prompt; empty for intermediate."""
    if user is None:
        return ""
    notes = [] if user.level == "intermediate" else [prompt(f"level_{user.level}")]
    if user.name:
        notes.append(
            f"The user's name is {user.name}. Use it when you ask them a question or sum up."
        )
    return "".join(f"\n\n{n}" for n in notes)


def build_agent(
    tools: dict[str, BaseTool],
    model: ModelLike,
    checkpointer: BaseCheckpointSaver,
    models: dict[str, ModelLike] | None = None,
    user: UserContext | None = None,
    pin_macros: Callable[[], str] | None = None,
):
    """models: per-sub-agent overrides by name (e.g. a stronger model for parts-and-pins).
    user: whose level and name every prompt adapts to.
    pin_macros: read on every firmware model call, so the firmware agent sees the macros of the
    spec saved at that moment instead of guessing their names."""
    models = models or {}
    about = profile(user)
    firmware_middleware = []
    if pin_macros:

        @dynamic_prompt
        def with_pin_macros(request: ModelRequest) -> str:
            return f"{request.system_prompt}\n\n{pin_macros()}"

        firmware_middleware = [with_pin_macros]

    if isinstance(model, str):
        # The profile is looked up by the main model's spec string; instances (fakes) keep the default.
        register_harness_profile(
            model,
            HarnessProfile(
                general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)
            ),
        )
    subagents = [
        {
            "name": name,
            "description": description,
            # memory= reaches only the main agent, so sub-agents get the house rules inline.
            "system_prompt": f"{prompt(prompt_name)}\n\n{house_rules()}{about}",
            "tools": [tools[t] for t in tool_names],
            "model": model_spec(models.get(name, model)),
            "middleware": firmware_middleware if name == "firmware" else [],
        }
        for name, (prompt_name, description, tool_names) in SUBAGENTS.items()
    ]
    return create_deep_agent(
        model=model,
        tools=[tools[t] for t in ORCHESTRATOR_TOOLS],
        system_prompt=prompt("orchestrator") + about,
        middleware=[TodoListMiddleware()],
        subagents=subagents,
        memory=[AGENTS_MD],
        interrupt_on={"ask_user": {"allowed_decisions": ["respond"]}},
        checkpointer=checkpointer,
    )
