"""G2 gate: edits rerun only the stages they affect, and every artifact ends at the new spec rev."""

import pytest

from backend.contracts.parts import load_library
from backend.contracts.runner import run_dir_for
from backend.contracts.spec import UserContext
from tests.e2e.harness import saved_spec, start_edit, start_run, wait_for_done
from tests.e2e.test_plant_monitor import PROMPT
from tests.integration import invariants as inv

PROMPT_WITHOUT_BUZZER = (
    "A plant monitor for my desk: show soil moisture, temperature and humidity on a small "
    "screen. Budget about $30."
)
ENCLOSURE_STAGES = {"layout", "enclosure", "assembly"}

pytestmark = [
    pytest.mark.slow,
    pytest.mark.live,
    pytest.mark.xfail(
        reason="needs T20 (integration) and T22 (edit flow)", strict=False
    ),
]


def buzzer_refs(spec) -> set[str]:
    lib = load_library()
    return {p.ref for p in spec.parts if "buzzer" in lib.get(p.part_id).id}


async def run_then_edit(api, prompt: str, instruction: str):
    run_id = await start_run(api, prompt, UserContext(budget_usd=30.0))
    before = await wait_for_done(run_id)
    assert inv.failed_stages(before) == [], "the run before the edit must pass"
    old = saved_spec(run_id)
    await start_edit(api, run_id, instruction)
    events = await wait_for_done(run_id, after_seq=before[-1].seq)
    return run_id, old, events, before[-1].seq


async def test_wall_thickness_reruns_only_enclosure_stages(api):
    run_id, old, events, edit_seq = await run_then_edit(
        api, PROMPT, "make the walls 3 mm"
    )
    new = saved_spec(run_id)

    assert inv.check_events(events) == []
    assert new.rev > old.rev
    assert new.enclosure.wall_mm == 3.0
    for field in ("mcu", "parts", "connections", "firmware"):
        assert getattr(new, field) == getattr(old, field), (
            f"{field} changed on a wall edit"
        )
    edit_events = [e for e in events if e.seq > edit_seq]
    assert {e.stage for e in edit_events if e.status == "stale"} == ENCLOSURE_STAGES
    assert inv.stages_run(events, after_seq=edit_seq) == ENCLOSURE_STAGES | {"checks"}
    assert inv.failed_stages(events) == []
    assert inv.check_run_dir(run_dir_for(run_id)) == []  # every artifact at the new rev


async def test_add_a_buzzer_passes_every_check(api):
    run_id, old, events, edit_seq = await run_then_edit(
        api, PROMPT_WITHOUT_BUZZER, "add a buzzer that beeps when the soil is too dry"
    )
    new = saved_spec(run_id)

    assert not buzzer_refs(old), "precondition: the first run shouldn't have a buzzer"
    assert buzzer_refs(new), [p.part_id for p in new.parts]
    assert new.rev > old.rev
    assert inv.check_events(events) == []
    rerun = inv.stages_run(events, after_seq=edit_seq)
    must_rerun = {
        "validate",
        "layout",
        "enclosure",
        "assembly",
        "firmware",
        "wiring",
        "bom",
    }
    assert must_rerun <= rerun, f"didn't rerun {must_rerun - rerun}"
    assert inv.failed_stages(events) == []
    assert (
        inv.check_run_dir(run_dir_for(run_id)) == []
    )  # pins.h, cutouts, BOM, wiring include it
