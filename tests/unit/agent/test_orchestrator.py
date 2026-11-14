from langgraph.checkpoint.memory import InMemorySaver

from backend.agent.orchestrator import build_agent, model_spec, prompt
from backend.agent.tools import RunContext, make_tools
from backend.contracts.parts import load_library
from tests.unit.agent.conftest import FakeStageRunner


def test_only_the_three_specialists(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")  # builds the client; no request is sent
    ctx = RunContext("r1", lambda e: None, FakeStageRunner(), load_library(), "x")
    agent = build_agent(make_tools(ctx), model_spec("claude-test-model"), InMemorySaver())
    tools = agent.nodes["tools"].bound.tools_by_name
    task = tools["task"].description
    assert "- general-purpose:" not in task
    assert all(f"- {n}:" in task for n in ("parts-and-pins", "firmware", "enclosure"))
    assert {"write_todos", "ask_user", "price_bom"} <= set(tools)
    assert "write_spec" not in tools  # only the parts agent can write the spec


def test_model_spec_and_example_prompt(monkeypatch):
    monkeypatch.setenv("P2D_MODEL", "claude-x")
    assert model_spec() == "anthropic:claude-x"
    assert model_spec("openai:gpt") == "openai:gpt"
    assert '"part_id": "esp32_devkitc"' in prompt("parts")
