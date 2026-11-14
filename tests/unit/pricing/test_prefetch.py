import importlib.util
import json
from pathlib import Path

import respx

from backend.contracts.parts import PartLibrary, load_library
from backend.tools.pricing import GRAPHQL_URL, TOKEN_URL

SCRIPT = Path(__file__).resolve().parents[3] / "scripts/prefetch_prices.py"
_spec = importlib.util.spec_from_file_location("prefetch_prices", SCRIPT)
prefetch_prices = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prefetch_prices)


@respx.mock
def test_prefetch_writes_cache_with_fetched_at(tmp_path, monkeypatch):
    # Pin the library to one part so the single mocked offer maps to a known MPN,
    # however many parts the real library grows to.
    board = load_library().get("esp32_devkitc")
    monkeypatch.setattr(
        prefetch_prices, "load_library", lambda: PartLibrary({board.id: board})
    )
    respx.post(TOKEN_URL).respond(200, json={"access_token": "jwt"})
    seller = {
        "company": {"name": "Dist"},
        "offers": [
            {
                "clickUrl": "https://dist.example",
                "prices": [{"quantity": 1, "price": 9.5, "currency": "USD"}],
            }
        ],
    }
    respx.post(GRAPHQL_URL).respond(
        200,
        json={
            "data": {"supMultiMatch": [{"parts": [{"mpn": "x", "sellers": [seller]}]}]}
        },
    )
    out = tmp_path / "prices.json"
    prefetch_prices.prefetch(out, "id", "secret")
    cache = json.loads(out.read_text())
    assert cache["fetched_at"].startswith("20")
    assert cache["parts"] == {
        "ESP32-DEVKITC-32E": [
            {"breaks": [[1, 9.5]], "seller": "Dist", "url": "https://dist.example"}
        ]
    }
