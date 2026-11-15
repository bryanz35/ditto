from langgraph.checkpoint.memory import InMemorySaver

from backend.agent.orchestrator import build_agent, model_spec, prompt
from backend.agent.tools import RunContext, make_tools
from backend.contracts.parts import load_library
from tests.unit.agent.conftest import FakeStageRunner


def test_only_the_three_specialists(monkeypatch):
    monkeypatch.setenv(
        "ANTHROPIC_API_KEY", "dummy"
    )  # builds the client; no request is sent
    ctx = RunContext("r1", lambda e: None, FakeStageRunner(), load_library(), "x")
    agent = build_agent(
        make_tools(ctx), model_spec("claude-test-model"), InMemorySaver()
    )
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


def test_models_see_only_their_tools_and_specialists_report_json(monkeypatch):
    """The harness profile hides deepagents' filesystem tools (but read_file) from every agent,
    and a specialist's Report reaches the orchestrator as JSON."""
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    delegate = {"subagent_type": "firmware", "description": "x"}
    report = {
        "status": "done",
        "summary": "beeps when dry",
        "assumptions": ["USB power"],
    }
    replies = iter(
        [
            AIMessage("", tool_calls=[{"name": "task", "args": delegate, "id": "t1"}]),
            AIMessage("", tool_calls=[{"name": "Report", "args": report, "id": "r1"}]),
            AIMessage("done"),
        ]
    )
    seen, results = [], []

    def generate(self, messages, stop=None, run_manager=None, **kw):
        seen.append({t["name"] for t in kw.get("tools", [])})
        results.extend(m.content for m in messages if isinstance(m, ToolMessage))
        return ChatResult(generations=[ChatGeneration(message=next(replies))])

    monkeypatch.setattr(ChatAnthropic, "_generate", generate)
    ctx = RunContext("r1", lambda e: None, FakeStageRunner(), load_library(), "x")
    agent = build_agent(
        make_tools(ctx), model_spec("claude-test-model"), InMemorySaver()
    )
    agent.invoke(
        {"messages": [{"role": "user", "content": "hi"}]},
        {"configurable": {"thread_id": "1"}},
    )

    main = {"task", "write_todos", "ask_user", "price_bom", "read_file"}
    firmware = {"write_firmware", "request_change", "read_file", "Report"}
    assert seen == [main, firmware, main]
    assert '"status":"done"' in results[-1].replace(" ", "")
    assert "USB power" in results[-1]
