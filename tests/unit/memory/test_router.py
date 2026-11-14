import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.routers.memory import get_store
from backend.memory.store import MemoryStore


@pytest.fixture
def client(tmp_path):
    app.dependency_overrides[get_store] = lambda: MemoryStore(tmp_path / "m.sqlite3")
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_get_put_round_trip(client):
    assert client.get("/memory").json() == {
        "budget_usd": None,
        "level": "intermediate",
        "name": None,
        "owned": {},
        "printer": None,
        "rejected": [],
    }
    body = {
        "budget_usd": 25.0,
        "level": "beginner",
        "name": "Sam",
        "owned": {"esp32_devkitc": 1},
        "printer": "generic",
        "rejected": ["no buzzers"],
    }
    assert client.put("/memory", json=body).json() == body
    assert client.get("/memory").json() == body


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"owned": {"flux_capacitor": 1}}, "unknown part ids in owned: flux_capacitor"),
        ({"owned": {"esp32_devkitc": -1}}, "negative quantities"),
        ({"budget_usd": -5}, "budget_usd must be 0 or more"),
        ({"printer": "nope"}, "unknown printer 'nope'"),
        ({"owned": {"esp32_devkitc": "many"}}, None),  # Pydantic rejects the shape
    ],
)
def test_put_rejects_bad_values_and_saves_nothing(client, body, detail):
    reply = client.put("/memory", json=body)
    assert reply.status_code == 422
    if detail:
        assert detail in reply.json()["detail"]
    assert client.get("/memory").json()["owned"] == {}
