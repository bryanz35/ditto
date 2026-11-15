import json
from pathlib import Path

from backend.agent.tools import RunContext, make_tools
from backend.contracts.parts import load_library
from backend.contracts.results import ToolError, ToolResult
from backend.contracts.spec import UserContext
from tests.unit.agent.conftest import FakeStageRunner, fixture_spec_json


def _ctx(stages, events):
    return RunContext(
        run_id="r1",
        emit=events.append,
        run_stages=stages,
        lib=load_library(),
        prompt="plant monitor",
        user=UserContext(budget_usd=30),
    )


def test_fails_four_times_then_stops(events):
    bad = ToolResult(
        ok=False, errors=[ToolError(code="pin_conflict", message="GPIO21 twice")]
    )
    stages = FakeStageRunner(fail={"validate": bad})
    ctx = _ctx(stages, events)
    write_spec = make_tools(ctx)["write_spec"]

    replies = [write_spec.invoke({"spec_json": fixture_spec_json()}) for _ in range(5)]

    assert stages.calls == ["validate"] * 4  # 1 try + exactly 3 retries
    failed = [e for e in events if e.status == "failed"]
    assert [e.data["attempt"] for e in failed] == [1, 2, 3, 4]
    assert "GPIO21 twice" in replies[0]
    assert replies[4].startswith("Retry limit reached")
    assert not ctx.spec_path.exists()  # nothing unchecked reaches the run folder


def test_write_spec_saves_with_code_owned_fields(events):
    ctx = _ctx(FakeStageRunner(), events)
    tools = make_tools(ctx)

    assert (
        tools["write_spec"]
        .invoke({"spec_json": fixture_spec_json()})
        .startswith("PASSED")
    )
    spec = ctx.load_spec()
    assert (spec.rev, spec.prompt, spec.user.budget_usd) == (1, "plant monitor", 30)
    assert all(e.data["attempt"] == 1 for e in events)

    assert tools["set_enclosure"].invoke({"wall_mm": 3.0}).startswith("PASSED")
    assert (ctx.load_spec().rev, ctx.load_spec().enclosure.wall_mm) == (2, 3.0)
    # every rev kept whole for the engine; no temp file left behind
    folder = ctx.spec_path.parent
    assert sorted(p.name for p in (folder / "specs").iterdir()) == ["1.json", "2.json"]
    assert not (folder / "spec.json.tmp").exists()


def test_schema_errors_count_as_attempts(events):
    ctx = _ctx(FakeStageRunner(), events)
    reply = make_tools(ctx)["write_spec"].invoke({"spec_json": '{"title": "x"}'})
    assert reply.startswith("FAILED (attempt 1")
    assert events[-1].status == "failed" and events[-1].errors[0].code == "schema"


def test_write_firmware_updates_behaviors(events):
    ctx = _ctx(FakeStageRunner(), events)
    tools = make_tools(ctx)
    tools["write_spec"].invoke({"spec_json": fixture_spec_json()})
    reply = tools["write_firmware"].invoke(
        {"main_cpp": "// fw", "behaviors": ["beep twice when dry"]}
    )
    assert reply.startswith("PASSED")
    spec = ctx.load_spec()
    assert spec and (spec.rev, spec.firmware.behaviors) == (2, ["beep twice when dry"])
    assert (ctx.spec_path.parent / "firmware/src/main.cpp").read_text() == "// fw"


def test_retry_limit_leaves_main_cpp_alone(events):
    bad = ToolResult(ok=False, errors=[ToolError(code="compile", message="x")])
    ctx = _ctx(FakeStageRunner(fail={"firmware": bad}), events)
    tools = make_tools(ctx)
    tools["write_spec"].invoke({"spec_json": fixture_spec_json()})
    for i in range(4):
        tools["write_firmware"].invoke({"main_cpp": f"// try {i}"})
    main = ctx.spec_path.parent / "firmware/src/main.cpp"

    reply = tools["write_firmware"].invoke({"main_cpp": "// unchecked"})

    assert reply.startswith("Retry limit reached")
    assert main.read_text() == "// try 3"


BOOK = (
    Path(__file__).resolve().parents[3] / "fixtures/specs/book_holder.json"
).read_text()


def test_print_only_project_gets_its_shape_from_write_model(events):
    stages = FakeStageRunner()
    ctx = _ctx(stages, events)
    tools = make_tools(ctx)
    draft = json.loads(BOOK)
    draft["enclosure"] = {}  # the parts agent leaves the shape to the enclosure agent
    assert (
        tools["write_spec"]
        .invoke({"spec_json": json.dumps(draft)})
        .startswith("PASSED")
    )

    assert "no electronics" in tools["set_enclosure"].invoke({})
    assert "no electronics" in tools["write_firmware"].invoke({"main_cpp": "x"})
    assert "no electronics" in tools["price_bom"].invoke({})

    code = json.loads(BOOK)["enclosure"]["code"]
    assert tools["write_model"].invoke({"code": code}).startswith("PASSED")
    spec = ctx.load_spec()
    assert (spec.rev, spec.enclosure.template, spec.enclosure.code) == (
        2,
        "custom",
        code,
    )
    assert stages.calls == ["validate", "enclosure"]  # no layout without electronics


def test_firmware_prompt_carries_part_snippets(events):
    ctx = _ctx(FakeStageRunner(), events)
    assert "Known-good" not in ctx.pin_macros()  # no spec yet
    make_tools(ctx)["write_spec"].invoke({"spec_json": fixture_spec_json()})

    macros = ctx.pin_macros()
    assert "bme.begin(0x76" in macros  # bme280_breakout's snippet
    assert "env1 (" in macros and "Adafruit BME280" in macros  # its pio_lib_deps
    assert macros.count("Known-good example for env1") == 1
