import pytest

from tests.e2e.harness import api_client


@pytest.fixture
async def api(tmp_path, monkeypatch):
    """The real app with the real runner, writing runs under tmp_path."""
    monkeypatch.setenv("P2D_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("P2D_RUNNER", "real")
    async with api_client() as client:
        yield client
