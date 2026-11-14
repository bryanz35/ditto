"""Fakes for agent tests: a StageRunner on fake_toolbox() and scripted chat models."""

import json
from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from backend.contracts.events import Event
from backend.contracts.parts import load_library
from backend.contracts.results import ToolResult
from backend.contracts.runner import run_dir_for
from backend.tools.fakes import fake_toolbox

FIXTURE_SPEC = Path(__file__).resolve().parents[3] / "fixtures/specs/plant_monitor.json"


class FakeStageRunner:
    """Runs the stages the agent tools need through fake_toolbox(), emitting like T14's run_stages.
    `fail` maps a stage to a ToolResult it returns instead."""

    def __init__(self, fail: dict[str, ToolResult] | None = None):
        self.toolbox, self.lib = fake_toolbox(), load_library()
        self.fail = fail or {}
        self.calls: list[str] = []

    def __call__(self, run_id, stages, spec, emit):
        run_dir, tb, results = run_dir_for(run_id), self.toolbox, {}
        for stage in stages:
            self.calls.append(stage)
            emit(Event(run_id=run_id, stage=stage, status="running", spec_rev=spec.rev))
            r = self.fail.get(stage) or self._run(stage, spec, run_dir, tb)
            status = "passed" if r.ok else "skipped" if r.skipped else "failed"
            emit(
                Event(
                    run_id=run_id,
                    stage=stage,
                    status=status,
                    spec_rev=spec.rev,
                    errors=r.errors,
                )
            )
            results[stage] = r
        return results

    def _run(self, stage, spec, run_dir: Path, tb) -> ToolResult:
        if stage == "validate":
            return tb.validate_spec(spec, self.lib)
        if stage == "firmware":
            main = (run_dir / "firmware/src/main.cpp").read_text()
            return tb.write_firmware_project(spec, self.lib, main, run_dir / "firmware")
        if stage == "layout":
            return tb.compute_layout(spec, self.lib, run_dir / "cad")
        if stage == "enclosure":
            return tb.build_enclosure(spec, None, self.lib, run_dir / "cad")
        if stage == "bom":
            return tb.price_bom(spec, self.lib, None, run_dir)
        return ToolResult(ok=True)


class ScriptedModel(GenericFakeChatModel):
    """Replays `messages` in order and records every prompt it was given."""

    seen: list[list[Any]] = []

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, *args, **kwargs):
        self.seen.append(messages)
        return super()._generate(messages, *args, **kwargs)


def script(*messages: AIMessage) -> ScriptedModel:
    return ScriptedModel(messages=iter(messages), seen=[])


def call(name: str, args: dict, id: str) -> AIMessage:
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": id}])


def fixture_spec_json() -> str:
    return json.dumps(json.loads(FIXTURE_SPEC.read_text()) | {"rev": 0})


@pytest.fixture(autouse=True)
def runs_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("P2D_RUNS_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def events() -> list[Event]:
    return []
