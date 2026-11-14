import asyncio
import json
from functools import partial

import httpx
import pytest

from backend.app.main import app
from backend.app.routers.runs import get_engine
from backend.contracts.hardware import Hardware
from backend.contracts.parts import load_library
from backend.runtime.replay_runner import ReplayRunner
from backend.runtime.runs import RunEngine
from backend.runtime.stages import run_stages
from backend.tools.fakes import fake_toolbox

MODE_V = Hardware(
    has_parts=None, has_printer=None, printer_model="generic", mode="V", simulate=True
)


@pytest.fixture
def runs_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("P2D_RUNS_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def engine(runs_dir):
    stage_runner = partial(
        run_stages, toolbox=fake_toolbox(), lib=load_library(), hardware=MODE_V
    )
    engine = RunEngine(ReplayRunner(delay_scale=0), stage_runner)
    app.dependency_overrides[get_engine] = lambda: engine
    yield engine
    app.dependency_overrides.clear()


@pytest.fixture
async def client(engine):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


async def read_stream(client, run_id, last_event_id=None):
    """The events of one SSE connection (it ends after `done`)."""
    headers = {"Last-Event-ID": str(last_event_id)} if last_event_id else {}
    get = client.get(f"/runs/{run_id}/events", headers=headers)
    response = await asyncio.wait_for(get, timeout=10)
    lines = response.text.splitlines()
    return [
        json.loads(x.removeprefix("data: ")) for x in lines if x.startswith("data: ")
    ]
