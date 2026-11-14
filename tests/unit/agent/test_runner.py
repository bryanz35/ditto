import asyncio

from langchain_core.messages import AIMessage

from backend.agent import AgentRunner
from backend.agent.runner import NO_ANSWER
from backend.contracts.runner import AnswerRequest, EditRequest, RunRequest
from backend.contracts.spec import ProjectSpec, UserContext
from backend.tools.fakes import fake_toolbox
from tests.unit.agent.conftest import (
    FakeStageRunner,
    call,
    fixture_spec_json,
    script,
)

PROMPT = "A plant monitor that beeps when the soil is dry"
TODOS = [
    {"content": "Choose parts and pins", "status": "in_progress"},
    {"content": "Firmware and enclosure", "status": "pending"},
]


def task(agent: str, id: str) -> dict:
    return {
        "name": "task",
        "args": {"description": f"do the {agent} work", "subagent_type": agent},
        "id": id,
    }


def runner(orchestrator, *, enclosure_calls=1, timeout=5.0) -> AgentRunner:
    """Specialists that each succeed with their one tool, as often as asked."""
    parts = script(
        call("write_spec", {"spec_json": fixture_spec_json()}, "p"),
        AIMessage("spec saved"),
    )
    firmware = script(
        call("write_firmware", {"main_cpp": '#include "pins.h"'}, "f"),
        AIMessage("fw ok"),
    )
    enclosure = script(
        *[
            m
            for i in range(enclosure_calls)
            for m in (
                call("set_enclosure", {"wall_mm": 2.0 + i}, f"e{i}"),
                AIMessage("case ok"),
            )
        ]
    )
    return AgentRunner(
        fake_toolbox(),
        orchestrator,
        FakeStageRunner(),
        models={"parts-and-pins": parts, "firmware": firmware, "enclosure": enclosure},
        question_timeout_s=timeout,
    )


def run_script(*extra: AIMessage):
    return script(
        call("write_todos", {"todos": TODOS}, "o1"),
        AIMessage("", tool_calls=[task("parts-and-pins", "o2")]),
        AIMessage("", tool_calls=[task("firmware", "o3"), task("enclosure", "o4")]),
        AIMessage("Built your plant monitor."),
        *extra,
    )


async def test_run_writes_spec_firmware_and_plan_events(runs_dir, events):
    spec = await runner(run_script()).run(
        RunRequest(run_id="r1", prompt=PROMPT, user=UserContext(budget_usd=30)),
        events.append,
    )

    assert (runs_dir / "r1/spec.json").exists()
    assert (runs_dir / "r1/firmware/src/main.cpp").read_text() == '#include "pins.h"'
    assert (
        ProjectSpec.model_validate_json((runs_dir / "r1/spec.json").read_text()) == spec
    )
    assert spec.rev == 2 and spec.prompt == PROMPT  # parts saved rev 1, enclosure rev 2
    plan = [e for e in events if e.stage == "plan"]
    assert any(e.data.get("todos") == TODOS for e in plan)
    assert plan[-1].status == "passed"
    assert {(e.stage, e.status) for e in events} >= {
        ("validate", "passed"),
        ("firmware", "passed"),
        ("enclosure", "passed"),
    }


async def test_edit_sees_earlier_conversation(events):
    orchestrator = run_script(
        AIMessage("", tool_calls=[task("enclosure", "o5")]),
        AIMessage("Walls are 3 mm now."),
    )
    agent = runner(orchestrator, enclosure_calls=2)
    first = await agent.run(RunRequest(run_id="r1", prompt=PROMPT), events.append)
    edit_starts = len(orchestrator.seen)

    edited = await agent.edit(
        "r1", EditRequest(instruction="make the walls 3 mm"), events.append
    )

    edit_prompt = " ".join(str(m.content) for m in orchestrator.seen[edit_starts])
    assert PROMPT in edit_prompt and "Built your plant monitor." in edit_prompt
    assert "make the walls 3 mm" in edit_prompt
    assert edited.rev == first.rev + 1 and edited.enclosure.wall_mm == 3.0


async def test_question_is_answered(events):
    orchestrator = run_script()
    orchestrator.messages = iter(
        [
            call(
                "ask_user",
                {"question": "USB or battery?", "options": ["USB", "Battery"]},
                "q",
            ),
            *orchestrator.messages,
        ]
    )
    agent = runner(orchestrator)

    def emit(e):
        events.append(e)
        if e.status == "waiting":
            q = e.data["question"]["id"]
            asyncio.get_running_loop().create_task(
                agent.answer("r1", AnswerRequest(question_id=q, answer="USB"))
            )

    await agent.run(RunRequest(run_id="r1", prompt=PROMPT), emit)

    waiting = next(e for e in events if e.status == "waiting")
    assert waiting.stage == "plan" and waiting.data["question"]["options"] == [
        "USB",
        "Battery",
    ]
    tool_replies = [m.content for m in orchestrator.seen[-1] if m.type == "tool"]
    assert "USB" in tool_replies


async def test_unanswered_question_times_out(events):
    orchestrator = run_script()
    orchestrator.messages = iter(
        [
            call("ask_user", {"question": "Battery?", "options": []}, "q"),
            *orchestrator.messages,
        ]
    )

    await runner(orchestrator, timeout=0.01).run(
        RunRequest(run_id="r1", prompt=PROMPT), events.append
    )

    assert any("No answer after" in e.message for e in events)
    assert NO_ANSWER in [m.content for m in orchestrator.seen[-1] if m.type == "tool"]
