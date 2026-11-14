import asyncio
import threading

from backend.contracts.events import Event
from backend.contracts.runner import RunRequest
from backend.runtime.replay_runner import ReplayRunner
from backend.runtime.runs import CANCELLED, RunCancelled, RunEngine, read_events
from tests.unit.api.conftest import read_stream


async def start(client):
    response = await client.post("/runs", data={"prompt": "a plant monitor"})
    assert response.status_code == 200
    return response.json()["run_id"]


async def test_list_runs_newest_first(client, runs_dir):
    (runs_dir / "junk").mkdir()  # no events: not listed
    first = await start(client)
    await read_stream(client, first)
    second = await start(client)
    await read_stream(client, second)

    runs = (await client.get("/runs")).json()
    assert [r["run_id"] for r in runs] == [second, first]
    assert runs[0]["title"] == "Plant monitor"
    assert (runs[0]["stage"], runs[0]["status"], runs[0]["spec_rev"]) == (
        "done",
        "passed",
        2,
    )
    assert runs[0]["ts"] >= runs[1]["ts"] > 0


async def test_cancel_ends_stream(client, engine):
    engine.runner.delay_scale = (
        1  # replay the recorded gaps, so the run is still working
    )
    run_id = await start(client)
    await asyncio.sleep(0.1)
    assert (await client.post(f"/runs/{run_id}/cancel")).status_code == 202

    events = await read_stream(client, run_id)
    assert (events[-1]["stage"], events[-1]["status"]) == ("done", "failed")
    assert events[-1]["message"] == CANCELLED
    assert not engine.busy(run_id)
    assert (await client.post(f"/runs/{run_id}/cancel")).status_code == 409
    assert (await client.post("/runs/nope/cancel")).status_code == 404


async def test_cancel_stops_stage_thread(runs_dir):
    started, release, finished, late = (*(threading.Event() for _ in range(3)), [])

    def stage_runner(run_id, stages, spec, emit):
        started.set()
        release.wait(5)
        try:
            emit(Event(run_id=run_id, stage="validate", status="running"))
        except RunCancelled as exc:
            late.append(exc)
        finished.set()
        return {}

    engine = RunEngine(ReplayRunner(delay_scale=0), stage_runner)
    engine.start(RunRequest(run_id="r1", prompt="x"))
    assert await asyncio.to_thread(started.wait, 5)
    engine.cancel("r1")
    while engine.busy("r1"):
        await asyncio.sleep(0.01)
    release.set()
    assert await asyncio.to_thread(finished.wait, 5)

    assert late  # the stage thread's event after the cancel was refused
    last = read_events("r1")[-1]
    assert (last.stage, last.status, last.message) == ("done", "failed", CANCELLED)


def test_read_events_skips_a_half_written_line(runs_dir):
    line = Event(run_id="r1", seq=1, stage="plan", status="running").model_dump_json()
    (runs_dir / "r1").mkdir()
    (runs_dir / "r1" / "events.jsonl").write_text(line + "\n" + line[:20])
    assert [e.seq for e in read_events("r1")] == [1]


async def test_replay_keeps_cad_manifest(client, runs_dir):
    run_id = await start(client)
    await read_stream(client, run_id)
    assert (runs_dir / run_id / "cad" / "manifest.json").is_file()
