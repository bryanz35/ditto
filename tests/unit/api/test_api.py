import asyncio

from backend.contracts.events import Event
from backend.runtime.deps import ORDER
from backend.runtime.replay_runner import ReplayRunner
from backend.runtime.runs import engine_from_env
from tests.unit.api.conftest import read_stream


async def start(client):
    response = await client.post("/runs", data={"prompt": "a plant monitor"})
    assert response.status_code == 200
    return response.json()["run_id"]


async def test_fake_runner_streams_a_complete_run(client, monkeypatch):
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "WOKWI_CLI_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    run_id = await start(client)
    events = await read_stream(client, run_id)

    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert {e["run_id"] for e in events} == {run_id}
    assert events[-1]["stage"] == "done" and events[-1]["status"] == "passed"
    last = {e["stage"]: e["status"] for e in events}
    assert all(last[s] == "passed" for s in [*ORDER, "checks"])
    assert any(e["status"] == "failed" for e in events)  # the recorded retry
    assert (await client.get(f"/runs/{run_id}/spec")).json()["rev"] == 2
    stl = await client.get(f"/runs/{run_id}/files/cad/base.stl")
    assert stl.status_code == 200 and stl.content
    manifest = (await client.get(f"/runs/{run_id}/files/manifest.json")).json()
    assert manifest["spec_rev"] == 2
    assert manifest["artifacts"]["bom_json"]["path"] == "bom.json"


def test_p2d_runner_fake_needs_no_keys(monkeypatch):
    monkeypatch.setenv("P2D_RUNNER", "fake")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert isinstance(engine_from_env().runner, ReplayRunner)


async def test_last_event_id_resumes_without_duplicates(client):
    run_id = await start(client)
    everything = await read_stream(client, run_id)
    resumed = await read_stream(client, run_id, last_event_id=10)
    assert [e["seq"] for e in resumed] == [
        e["seq"] for e in everything if e["seq"] > 10
    ]


async def test_path_traversal_is_rejected(client, runs_dir):
    (runs_dir / "secret.txt").write_text("no")
    run_id = await start(client)
    await read_stream(client, run_id)
    for url in (
        f"/runs/{run_id}/files/%2e%2e/secret.txt",
        f"/runs/{run_id}/files/..%2fsecret.txt",
        f"/runs/{run_id}/files/%2fetc%2fpasswd",
        "/runs/%2e%2e/files/secret.txt",
        "/runs/nope/spec",
    ):
        assert (await client.get(url)).status_code == 404, url


async def test_edit_bumps_rev_and_reruns(client):
    run_id = await start(client)
    first = await read_stream(client, run_id)
    response = await client.post(
        f"/runs/{run_id}/edit", json={"instruction": "walls 3 mm"}
    )
    assert response.status_code == 202
    second = await read_stream(client, run_id, last_event_id=first[-1]["seq"])
    assert second[-1]["stage"] == "done" and second[-1]["spec_rev"] == 3
    assert {e["stage"] for e in second if e["status"] == "passed"} >= {*ORDER, "checks"}
    assert (await client.get(f"/runs/{run_id}/spec")).json()["rev"] == 3
    fresh = await read_stream(
        client, run_id
    )  # a new client gets both runs, not just the first
    assert fresh[-1] == second[-1]


async def test_edit_while_running_is_refused(client, engine):
    run_id = await start(client)
    assert engine.busy(run_id)
    response = await client.post(f"/runs/{run_id}/edit", json={"instruction": "x"})
    assert response.status_code == 409
    await read_stream(client, run_id)


async def test_answer_and_uploads(client, runs_dir):
    files = {"files": ("../sketch.png", b"png", "image/png")}
    response = await client.post(
        "/runs",
        data={"prompt": "p", "user_context": '{"budget_usd": 20}'},
        files=files,
    )
    run_id = response.json()["run_id"]
    assert (runs_dir / run_id / "input" / "sketch.png").read_bytes() == b"png"
    answer = {"question_id": "q1", "answer": "USB power"}
    assert (await client.post(f"/runs/{run_id}/answer", json=answer)).json() == {
        "ok": True
    }
    await asyncio.wait_for(read_stream(client, run_id), 10)


async def test_bad_user_context_is_a_422(client):
    data = {"prompt": "p", "user_context": '{"budget": 1}'}
    assert (await client.post("/runs", data=data)).status_code == 422


async def test_a_crashing_runner_still_ends_with_done(client, engine, monkeypatch):
    async def crash(request, emit):
        raise RuntimeError("model down")

    monkeypatch.setattr(engine.runner, "run", crash)
    events = await read_stream(client, await start(client))
    assert events[-1]["stage"] == "done" and events[-1]["status"] == "failed"
    assert "model down" in events[-1]["message"]
    assert events[-1]["spec_rev"] == 0  # nothing saved yet


def test_manifest_follows_the_saved_spec_not_a_failed_draft(engine, runs_dir):
    run_dir = runs_dir / "r1"
    run_dir.mkdir()
    (run_dir / "spec.json").write_text('{"rev": 2}')
    emit = engine.emitter("r1")
    emit(
        Event(
            run_id="r1",
            stage="bom",
            status="passed",
            message="",
            spec_rev=2,
            artifacts={"bom_json": "bom.json"},
        )
    )
    emit(
        Event(
            run_id="r1", stage="validate", status="failed", message="draft", spec_rev=3
        )
    )
    manifest = (run_dir / "manifest.json").read_text()
    assert '"spec_rev": 2' in manifest and '"spec_rev": 3' not in manifest
