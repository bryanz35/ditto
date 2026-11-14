"""The invariant helpers accept the hand-checked fixture run and catch each injected mismatch."""

import json
import shutil
from pathlib import Path

import pytest

from backend.contracts.parts import load_library
from tests.integration import invariants as inv

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
RUN = FIXTURES / "runs" / "plant_monitor"


@pytest.fixture(scope="module")
def lib():
    return load_library()


@pytest.fixture
def run_copy(tmp_path) -> Path:
    return Path(shutil.copytree(RUN, tmp_path / "run"))


def edit_json(path: Path, change) -> None:
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data))


def test_fixture_run_is_consistent(lib):
    assert inv.check_run_dir(RUN, lib) == []


def test_fixture_run_events():
    events = inv.load_events(RUN / "events.jsonl")
    assert inv.check_events(events) == []
    assert inv.failed_stages(events) == []
    assert events[0].seq == 1


def test_edit_fixture_reruns_only_enclosure_stages():
    run = inv.load_events(FIXTURES / "events" / "plant_monitor.jsonl")
    edit = inv.load_events(FIXTURES / "events" / "plant_monitor_edit.jsonl")
    assert inv.check_events(run + edit) == []
    rerun = inv.stages_run(run + edit, after_seq=run[-1].seq)
    assert rerun == {"layout", "enclosure", "assembly", "checks"}
    stale = {e.stage for e in edit if e.status == "stale"}
    assert stale == {"layout", "enclosure", "assembly"}


def test_failed_stage_is_reported():
    events = inv.load_events(RUN / "events.jsonl")
    firmware = next(e for e in reversed(events) if e.stage == "firmware")
    broken = [
        e.model_copy(update={"status": "failed"}) if e is firmware else e
        for e in events
    ]
    assert [p.split(":")[0] for p in inv.failed_stages(broken)] == ["firmware"]
    skipped = [
        e.model_copy(update={"status": "skipped"}) if e is firmware else e
        for e in events
    ]
    assert inv.failed_stages(skipped) != []  # only simulate may be skipped


def test_events_out_of_order_are_reported():
    events = inv.load_events(RUN / "events.jsonl")
    assert inv.check_events(events[:5] + events[6:])  # seq gap
    assert inv.check_events(events[:-1])  # no done


def _break_pins(run: Path):
    pins = run / "firmware/include/pins.h"
    pins.write_text(
        pins.read_text().replace("PIN_BUZZER1_SIG 25", "PIN_BUZZER1_SIG 26")
    )


def _extra_pin(run: Path):
    pins = run / "firmware/include/pins.h"
    pins.write_text(pins.read_text() + "#define PIN_LED1_SIG 4\n")


def _drop_cutout(run: Path):
    edit_json(run / "cad/manifest.json", lambda m: m["cutouts"].pop(0))


def _drop_cable_hole(run: Path):
    edit_json(
        run / "cad/manifest.json",
        lambda m: m.update(
            cutouts=[c for c in m["cutouts"] if c["for_ref"] != "soil1"]
        ),
    )


def _cutout_off_face(run: Path):
    edit_json(
        run / "cad/manifest.json",
        lambda m: m["cutouts"][0].update(center_mm=[500.0, 5.0]),
    )


def _drop_bom_line(run: Path):
    edit_json(run / "bom.json", lambda b: b["lines"].pop())


def _wrong_bom_total(run: Path):
    edit_json(run / "bom.json", lambda b: b.update(total_usd=99.0))


def _overlap(run: Path):
    def move(layout):
        oled = next(p for p in layout["placements"] if p["ref"] == "oled1")
        oled["x_mm"] = 10.0

    edit_json(run / "cad/layout.json", move)


def _outside_cavity(run: Path):
    edit_json(
        run / "cad/layout.json", lambda lay: lay.update(cavity_mm=[60.0, 45.94, 16.0])
    )


def _not_against_wall(run: Path):
    def move(layout):
        esp = next(p for p in layout["placements"] if p["ref"] == "esp32")
        esp["x_mm"] = 0.5

    edit_json(run / "cad/layout.json", move)


def _stale_artifact(run: Path):
    edit_json(
        run / "manifest.json", lambda m: m["artifacts"]["pins_h"].update(spec_rev=1)
    )


def _missing_artifact(run: Path):
    (run / "cad/assembly.glb").unlink()


def _wiring_row_dropped(run: Path):
    edit_json(run / "wiring.json", lambda w: w["rows"].pop())


def _spec_rev_bumped(run: Path):
    edit_json(run / "spec.json", lambda s: s.update(rev=3))


@pytest.mark.parametrize(
    "inject",
    [
        _break_pins,
        _extra_pin,
        _drop_cutout,
        _drop_cable_hole,
        _cutout_off_face,
        _drop_bom_line,
        _wrong_bom_total,
        _overlap,
        _outside_cavity,
        _not_against_wall,
        _stale_artifact,
        _missing_artifact,
        _wiring_row_dropped,
        _spec_rev_bumped,
    ],
)
def test_injected_mismatch_is_caught(run_copy, lib, inject):
    inject(run_copy)
    assert inv.check_run_dir(run_copy, lib)
