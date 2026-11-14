"""T22: an edit marks only the stages its changed spec fields affect as stale, reruns them through
run_stages without the model, and carries every other artifact forward to the new rev."""

import asyncio
import json
from functools import partial

from backend.contracts.events import Event
from backend.contracts.invariants import check_events, check_run_dir, stages_run
from backend.contracts.parts import load_library
from backend.contracts.runner import EditRequest, NoSpec, RunRequest, run_dir_for
from backend.contracts.spec import ProjectSpec
from backend.runtime.replay_runner import ReplayRunner
from backend.runtime.runs import RunEngine, read_events
from backend.runtime.stages import run_stages
from backend.tools.fakes import fake_toolbox
from tests.unit.api.conftest import MODE_V

ENCLOSURE_STAGES = {"layout", "enclosure", "assembly"}
PIN_STAGES = {"validate", "firmware", "wiring", "simulate"}


class CountingRunner(ReplayRunner):
    """The Runner is the only code that holds the model, so every call into it counts as model work.
    patch(spec) stands in for the model's edit; firmware_passed emits what the firmware sub-agent
    emits after rewriting main.cpp."""

    def __init__(self, patch=None, firmware_passed=False):
        super().__init__(delay_scale=0)
        self.model_calls = 0
        self.patch, self.firmware_passed = patch, firmware_passed

    async def run(self, request, emit):
        self.model_calls += 1
        return await super().run(request, emit)

    async def edit(self, run_id, request, emit):
        self.model_calls += 1
        if self.patch is None:
            return await super().edit(run_id, request, emit)
        path = run_dir_for(run_id) / "spec.json"
        spec = ProjectSpec.model_validate_json(path.read_text())
        spec = self.patch(spec).model_copy(update={"rev": spec.rev + 1})
        path.write_text(spec.model_dump_json(indent=2) + "\n")
        if self.firmware_passed:
            emit(
                Event(
                    run_id=run_id, stage="firmware", status="passed", spec_rev=spec.rev
                )
            )
        return spec


def make_engine(runner) -> RunEngine:
    stages = partial(
        run_stages, toolbox=fake_toolbox(), lib=load_library(), hardware=MODE_V
    )
    return RunEngine(runner, stages)


async def finish(engine: RunEngine, run_id: str) -> None:
    while engine.busy(run_id):
        await asyncio.sleep(0.01)


async def run_then_edit(runner, runs_dir, engine=None):
    """A full fake run, then an edit; returns the events after the edit and the model calls made
    once runner.edit() had returned."""
    engine = engine or make_engine(runner)
    engine.start(RunRequest(run_id="r1", prompt="a plant monitor"))
    await finish(engine, "r1")
    edit_seq = read_events("r1")[-1].seq
    engine.edit("r1", EditRequest(instruction="make the walls 3 mm"))
    await finish(engine, "r1")
    return read_events("r1", edit_seq), runner.model_calls - 2  # run() and edit()


def stale(events) -> set[str]:
    return {e.stage for e in events if e.status == "stale"}


async def test_wall_edit_reruns_only_enclosure_stages_without_the_model(runs_dir):
    events, calls_after_edit = await run_then_edit(CountingRunner(), runs_dir)

    assert calls_after_edit == 0
    assert stale(events) == ENCLOSURE_STAGES
    assert stages_run(events) == ENCLOSURE_STAGES | {"checks"}
    assert check_events(read_events("r1")) == []
    run_dir = run_dir_for("r1")
    # bom, wiring, firmware carried to the new rev (the fake enclosure copies the 2 mm fixture
    # files, so only rev problems are checked here; Q's e2e test checks everything)
    assert [p for p in check_run_dir(run_dir) if "rev" in p] == []
    assert json.loads((run_dir / "bom.json").read_text())["spec_rev"] == 3


def move_soil_pin(spec: ProjectSpec) -> ProjectSpec:
    conns = [
        c.model_copy(update={"mcu_pin": "GPIO33"})
        if c.part_ref == "soil1" and c.bus == "analog"
        else c
        for c in spec.connections
    ]
    assert conns != spec.connections
    return spec.model_copy(update={"connections": conns})


async def test_pins_only_edit_reruns_firmware_without_the_model(runs_dir):
    events, calls_after_edit = await run_then_edit(
        CountingRunner(move_soil_pin), runs_dir
    )

    assert calls_after_edit == 0
    assert stale(events) == PIN_STAGES
    assert stages_run(events) == PIN_STAGES | {"checks"}
    assert events[-1].stage == "done" and events[-1].status == "passed"


def change_behaviour(spec: ProjectSpec) -> ProjectSpec:
    fw = spec.firmware.model_copy(update={"behaviors": ["Beep once an hour"]})
    return spec.model_copy(update={"firmware": fw})


async def test_stage_the_runner_already_passed_at_the_new_rev_is_skipped(runs_dir):
    runner = CountingRunner(change_behaviour, firmware_passed=True)
    events, _ = await run_then_edit(runner, runs_dir)

    assert stale(events) == {"validate", "firmware", "simulate"}
    assert stages_run(events) == {"validate", "simulate", "checks"}
    firmware = [e.status for e in events if e.stage == "firmware"]
    assert firmware == ["passed", "stale", "passed"]  # the UI never ends on stale
    assert events[-1].status == "passed"


async def test_edit_after_an_api_restart_still_reruns_only_what_it_affects(runs_dir):
    runner = CountingRunner()
    engine = make_engine(runner)
    engine.start(RunRequest(run_id="r1", prompt="a plant monitor"))
    await finish(engine, "r1")
    edit_seq = read_events("r1")[-1].seq

    restarted = make_engine(runner)
    restarted.edit("r1", EditRequest(instruction="make the walls 3 mm"))
    await finish(restarted, "r1")

    events = read_events("r1", edit_seq)
    assert stages_run(events) == ENCLOSURE_STAGES | {"checks"}
    assert check_events(read_events("r1")) == []


async def test_editing_a_run_that_never_saved_a_spec_restarts_it(runs_dir):
    (
        runs_dir / "r1"
    ).mkdir()  # failed before spec.json (and, in older runs, request.json)
    runner = CountingRunner()
    engine = make_engine(runner)
    engine.edit("r1", EditRequest(instruction="make the walls 3 mm"))
    await finish(engine, "r1")

    last = read_events("r1")[-1]
    assert (last.stage, last.status) == ("done", "passed")
    assert runner.model_calls == 1  # run(), not edit()


class FailingRunner(ReplayRunner):
    """run() fails before saving a spec its first `failures` times, like a model API error."""

    def __init__(self, failures):
        super().__init__(delay_scale=0)
        self.failures, self.prompts = failures, []

    async def run(self, request, emit):
        self.prompts.append(request.prompt)
        if len(self.prompts) <= self.failures:
            raise RuntimeError("model unavailable")
        return await super().run(request, emit)


async def test_a_run_that_stops_says_why_and_tries_again(runs_dir):
    runner = FailingRunner(failures=1)
    engine = make_engine(runner)
    engine.start(RunRequest(run_id="r1", prompt="a plant monitor"))
    await finish(engine, "r1")

    assert len(runner.prompts) == 2
    assert runner.prompts[1].startswith("a plant monitor\n\n")
    assert "RuntimeError: model unavailable" in runner.prompts[1]
    events = read_events("r1")
    [note] = [e for e in events if e.stage == "plan" and e.data.get("attempt") == 1]
    assert note.status == "failed"
    assert "stopped on an error: RuntimeError: model unavailable" in note.message
    assert "Trying again (2 of 3)" in note.message
    assert (events[-1].stage, events[-1].status) == ("done", "passed")
    assert check_events(events) == []


async def test_a_run_that_keeps_stopping_gives_up_then_a_message_restarts_it(runs_dir):
    runner = FailingRunner(failures=3)
    engine = make_engine(runner)
    engine.start(RunRequest(run_id="r1", prompt="a plant monitor"))
    await finish(engine, "r1")
    last = read_events("r1")[-1]
    assert (last.stage, last.status) == ("done", "failed")
    assert "I tried 3 times" in last.message
    assert len(runner.prompts) == 3

    engine.edit("r1", EditRequest(instruction="try again"))
    await finish(engine, "r1")
    assert runner.prompts[3] == "a plant monitor\n\ntry again"
    [said] = [e for e in read_events("r1") if e.data.get("chat") == "user"]
    assert (said.stage, said.status, said.message) == ("plan", "queued", "try again")
    assert read_events("r1")[-1].status == "passed"


class AsksFirstRunner(ReplayRunner):
    """run() ends without a spec on purpose the first time, like an agent asking what to build."""

    def __init__(self):
        super().__init__(delay_scale=0)
        self.calls = 0

    async def run(self, request, emit):
        self.calls += 1
        if self.calls == 1:
            raise NoSpec("asked what to build")
        return await super().run(request, emit)


async def test_a_run_the_agent_ends_without_a_spec_waits_for_the_user(runs_dir):
    runner = AsksFirstRunner()
    engine = make_engine(runner)
    engine.start(RunRequest(run_id="r1", prompt="a gadget"))
    await finish(engine, "r1")
    last = read_events("r1")[-1]
    assert (last.stage, last.status, last.message) == (
        "done",
        "failed",
        "Waiting for your reply",
    )
    assert runner.calls == 1  # not retried

    engine.edit("r1", EditRequest(instruction="a plant monitor"))
    await finish(engine, "r1")
    assert read_events("r1")[-1].status == "passed"
