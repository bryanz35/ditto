import asyncio

import pytest
from langchain_core.messages import AIMessage

from backend.agent import AgentRunner
from backend.agent.runner import NO_ANSWER
from backend.contracts.results import ToolError, ToolResult
from backend.contracts.runner import (
    AnswerRequest,
    AskRequest,
    ChatTurn,
    EditRequest,
    NoSpec,
    RunRequest,
)
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
    write = call("write_spec", {"spec_json": fixture_spec_json()}, "p")
    parts = script(write, AIMessage("spec saved"), write, AIMessage("spec saved"))
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
    [reply] = [e for e in plan if e.data.get("chat") == "agent"]
    assert reply.message == "Built your plant monitor."
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


async def test_failed_edit_keeps_the_spec_and_says_why(runs_dir, events):
    orchestrator = run_script(
        AIMessage("", tool_calls=[task("parts-and-pins", "o5")]),
        AIMessage("Couldn't add it."),
    )
    agent = runner(orchestrator)
    first = await agent.run(RunRequest(run_id="r1", prompt=PROMPT), events.append)
    bad = ToolResult(ok=False, errors=[ToolError(code="pin_conflict", message="x")])
    agent.run_stages.fail["validate"] = bad
    events.clear()

    spec = await agent.edit(
        "r1", EditRequest(instruction="add a buzzer"), events.append
    )

    assert spec == first
    assert [(e.stage, e.status, e.data.get("chat")) for e in events][-3:] == [
        ("validate", "failed", None),
        ("plan", "running", "agent"),
        ("plan", "passed", None),
    ]
    assert events[-2].message == "Couldn't add it."
    assert agent.run_stages.calls.count("validate") == 2
    saved = ProjectSpec.model_validate_json((runs_dir / "r1/spec.json").read_text())
    assert saved == first  # the failed draft never reached spec.json


async def test_a_run_that_ends_without_a_spec_says_why(runs_dir, events):
    reply = "There's no joystick in the parts library: should I use four buttons?"
    agent = runner(script(AIMessage(reply)))

    with pytest.raises(NoSpec):
        await agent.run(RunRequest(run_id="r1", prompt="a joystick"), events.append)

    assert [(e.message, e.data.get("chat")) for e in events][-2:] == [
        (reply, "agent"),
        ("No validated spec yet", None),
    ]


def system_prompt(model) -> str:
    return model.seen[0][0].text


async def test_prompts_adapt_to_level_and_name(events):
    orchestrator = run_script()
    agent = runner(orchestrator)
    user = UserContext(level="beginner", name="Ada")

    await agent.run(RunRequest(run_id="r1", prompt=PROMPT, user=user), events.append)

    parts = agent.models["parts-and-pins"]
    for model in (orchestrator, parts):
        assert "The user is a beginner" in system_prompt(model)
    assert "The user's name is Ada." in system_prompt(orchestrator)


async def test_intermediate_adds_nothing(events):
    orchestrator = run_script()
    await runner(orchestrator).run(
        RunRequest(run_id="r1", prompt=PROMPT), events.append
    )

    assert "The user is" not in system_prompt(orchestrator)
    assert "The user's name" not in system_prompt(orchestrator)


async def test_edit_keeps_the_runs_level(events):
    orchestrator = run_script(
        AIMessage("", tool_calls=[task("enclosure", "o5")]),
        AIMessage("Walls are 3 mm now."),
    )
    agent = runner(orchestrator, enclosure_calls=2)
    user = UserContext(level="expert")
    await agent.run(RunRequest(run_id="r1", prompt=PROMPT, user=user), events.append)
    edit_starts = len(orchestrator.seen)

    edited = await agent.edit(
        "r1", EditRequest(instruction="make the walls 3 mm"), events.append
    )

    assert edited.user.level == "expert"
    assert "The user is an expert" in orchestrator.seen[edit_starts][0].text


async def test_firmware_agent_sees_the_saved_specs_pin_macros(events):
    """The G1 live run guessed PIN_BZ1_POSITIVE; the prompt must list what pins.h defines."""
    r = runner(run_script())
    await r.run(RunRequest(run_id="r1", prompt=PROMPT), events.append)

    system = r.models["firmware"].seen[0][0]
    assert system.type == "system"
    assert "pins.h for the saved spec defines exactly these macros" in system.content
    assert "- PIN_BUZZER1_SIG (GPIO" in system.content
    assert "PIN_ENV1_VCC" not in system.content  # power pins get no macro


async def test_past_projects_reach_every_agent(events, tmp_path, monkeypatch):
    project = tmp_path / "pack" / "projects" / "arm.md"
    project.parent.mkdir(parents=True)
    project.write_text("# Servo arm")
    (tmp_path / "pack" / "fetch.py").write_text("")
    monkeypatch.setattr("backend.agent.orchestrator.REFERENCES", tmp_path)
    path = "/references/pack/projects/arm.md"
    orchestrator = run_script()
    orchestrator.messages = iter(
        [call("read_file", {"file_path": path}, "o0"), *orchestrator.messages]
    )
    r = runner(orchestrator)

    await r.run(RunRequest(run_id="r1", prompt=PROMPT), events.append)

    listed = f"- `{path}`"
    assert listed in system_prompt(orchestrator)  # via the AGENTS.md memory
    for name in ("parts-and-pins", "firmware", "enclosure"):
        assert listed in system_prompt(r.models[name])
    assert "fetch.py" not in system_prompt(orchestrator)
    read = orchestrator.seen[1][-1]
    assert read.type == "tool" and "# Servo arm" in read.text


async def test_ask_answers_from_the_run_files_and_changes_nothing(runs_dir):
    run = runs_dir / "r1"
    (run / "firmware/src").mkdir(parents=True)
    (run / "spec.json").write_text(fixture_spec_json())
    (run / "firmware/src/main.cpp").write_text('#include "pins.h" // beep()')
    before = {p: p.read_text() for p in run.rglob("*") if p.is_file()}
    model = script(AIMessage("Use the **red** wire."))
    agent = AgentRunner(fake_toolbox(), model, FakeStageRunner())

    answer = await agent.ask(
        "r1",
        AskRequest(
            question="Which wire is VCC?",
            step="Step 8 of 12: Connect the screen (Wiring)",
            history=[
                ChatTurn(role="user", text="hi"),
                ChatTurn(role="ditto", text="hello"),
            ],
        ),
    )

    assert answer == "Use the **red** wire."
    [messages] = model.seen
    system, *history, question = messages
    assert "go back to Overview" in system.content and "beep()" in system.content
    assert ProjectSpec.model_validate_json(fixture_spec_json()).title in system.content
    assert [m.content for m in history] == ["hi", "hello"]
    assert (
        "Connect the screen" in question.content
        and "Which wire is VCC?" in question.content
    )
    assert {p: p.read_text() for p in run.rglob("*") if p.is_file()} == before
