import json
from pathlib import Path

import httpx
import pytest
import respx

from backend.contracts.artifacts import Bom
from backend.contracts.parts import load_library
from backend.contracts.spec import ProjectSpec
from backend.tools.pricing import GRAPHQL_URL, TOKEN_URL, price_bom

FIXTURE_SPEC = Path(__file__).resolve().parents[3] / "fixtures/specs/plant_monitor.json"
MPN = "ESP32-DEVKITC-32E"  # the only fixture part with an MPN; the rest have manual prices
LIB = load_library()


def spec(**user) -> ProjectSpec:
    s = ProjectSpec.model_validate_json(FIXTURE_SPEC.read_text())
    return s.model_copy(update={"user": s.user.model_copy(update=user)})


def offer(seller: str, breaks: list[list[float]]) -> dict:
    return {
        "seller": seller,
        "url": f"https://{seller}.example/esp32",
        "breaks": breaks,
    }


@pytest.fixture
def cache(tmp_path) -> Path:
    path = tmp_path / "prices.json"
    entry = [offer("cachedist", [[1, 8.0], [10, 7.0]])]
    path.write_text(
        json.dumps(
            {
                "fetched_at": "2026-11-13T09:00:00Z",
                "currency": "USD",
                "parts": {MPN: entry},
            }
        )
    )
    return path


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setenv("NEXAR_CLIENT_ID", "id")
    monkeypatch.setenv("NEXAR_CLIENT_SECRET", "secret")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """No credentials unless a test asks; any request without a mocked route fails the test."""
    monkeypatch.delenv("NEXAR_CLIENT_ID", raising=False)
    monkeypatch.delenv("NEXAR_CLIENT_SECRET", raising=False)
    with respx.mock(assert_all_called=False) as mock:
        yield mock


def line(result, part_id):
    return next(
        li for li in Bom.model_validate(result.data).lines if li.part_id == part_id
    )


def nexar_reply() -> dict:
    sellers = [
        {
            "company": {"name": "Pricey"},
            "offers": [
                {
                    "clickUrl": "https://pricey.example",
                    "prices": [
                        {"quantity": 1, "price": 12.0, "currency": "USD"},
                        {"quantity": 1, "price": 1.0, "currency": "EUR"},
                    ],
                }
            ],
        },
        {
            "company": {"name": "Bulk"},
            "offers": [
                {
                    "clickUrl": "https://bulk.example",
                    "prices": [
                        {"quantity": 10, "price": 6.5, "currency": "USD"},
                        {"quantity": 1, "price": 13.0, "currency": "USD"},
                    ],
                }
            ],
        },
    ]
    return {"data": {"supMultiMatch": [{"parts": [{"mpn": MPN, "sellers": sellers}]}]}}


def mock_nexar(mock, graphql: httpx.Response | Exception | None = None):
    mock.post(TOKEN_URL).respond(200, json={"access_token": "jwt"})
    route = mock.post(GRAPHQL_URL)
    if isinstance(graphql, Exception):
        route.side_effect = graphql
    else:
        route.mock(return_value=graphql or httpx.Response(200, json=nexar_reply()))
    return route


@pytest.mark.parametrize(
    "failure",
    [
        "token_401",
        httpx.Response(429, json={"message": "rate limited"}),
        httpx.ReadTimeout("timed out"),
        httpx.Response(200, json={"errors": [{"message": "bad query"}]}),
    ],
    ids=["401", "429", "timeout", "graphql_error"],
)
def test_nexar_failure_falls_back_to_cache_and_manual(
    failure, no_network, creds, cache, tmp_path
):
    if failure == "token_401":
        no_network.post(TOKEN_URL).respond(401, json={"error": "invalid_client"})
    else:
        mock_nexar(no_network, failure)
    result = price_bom(spec(), LIB, cache, tmp_path / "out")
    assert result.ok
    assert [e.code for e in result.errors] == ["live_prices_unavailable"]
    assert result.errors[0].severity == "warning"
    esp = line(result, "esp32_devkitc")
    assert (esp.price_source, esp.unit_price_usd) == ("cache", 8.0)
    assert line(result, "buzzer_passive").price_source == "manual"
    assert result.data["prices_fetched_at"] == "2026-11-13T09:00:00Z"


def test_nexar_failure_without_cache_uses_manual(no_network, creds, tmp_path):
    mock_nexar(no_network, httpx.ConnectError("offline"))
    result = price_bom(spec(), LIB, tmp_path / "absent.json", tmp_path / "out")
    assert result.ok
    esp = line(result, "esp32_devkitc")
    assert (esp.price_source, esp.unit_price_usd) == ("manual", 10.0)
    assert result.data["prices_fetched_at"] is None


def test_live_prices_use_quantity_breaks_and_cheapest_usd_offer(
    no_network, creds, cache, tmp_path
):
    graphql = mock_nexar(no_network)
    one = line(price_bom(spec(), LIB, cache, tmp_path / "a"), "esp32_devkitc")
    assert (one.price_source, one.unit_price_usd) == ("live", 12.0)  # EUR price ignored
    assert one.vendor_url == "https://pricey.example"
    sent = json.loads(graphql.calls[0].request.content)
    assert sent["variables"] == {"queries": [{"mpn": MPN, "limit": 1}]}
    assert graphql.calls[0].request.headers["token"] == "jwt"

    s = spec()
    many = s.model_copy(update={"mcu": s.mcu.model_copy(update={"qty": 10})})
    ten = line(price_bom(many, LIB, cache, tmp_path / "b"), "esp32_devkitc")
    assert (ten.unit_price_usd, ten.line_total_usd) == (6.5, 65.0)


def test_without_credentials_no_http_and_cache_is_used(no_network, cache, tmp_path):
    result = price_bom(spec(), LIB, cache, tmp_path)
    assert not no_network.calls
    assert result.ok and not result.errors
    assert line(result, "esp32_devkitc").price_source == "cache"


def test_owned_parts_cost_nothing_and_are_labelled(cache, tmp_path):
    s = spec(owned={"esp32_devkitc": 3, "buzzer_passive": 1})
    s = s.model_copy(
        update={"parts": [*s.parts, s.parts[0].model_copy(update={"ref": "env2"})]}
    )
    result = price_bom(s, LIB, cache, tmp_path)
    esp = line(result, "esp32_devkitc")
    assert (esp.qty, esp.owned_qty, esp.line_total_usd) == (1, 1, 0.0)
    assert esp.unit_price_usd == 8.0  # still shown
    env = line(result, "bme280_breakout")
    assert (env.refs, env.qty, env.owned_qty, env.line_total_usd) == (
        ["env1", "env2"],
        2,
        0,
        12.0,
    )
    assert result.data["total_usd"] == 12.0 + 5.0 + 2.5  # bme280 x2, oled, soil


@pytest.mark.parametrize(("budget", "over"), [(25.0, False), (24.99, True)])
def test_over_budget_at_the_boundary(budget, over, tmp_path):
    # Manual prices: 10 + 6 + 5 + 2.5 + 1.5 = 25.00
    result = price_bom(spec(budget_usd=budget), LIB, tmp_path / "none.json", tmp_path)
    assert result.data["total_usd"] == 25.0
    assert result.data["over_budget"] is over
    assert result.ok is not over
    assert ("over_budget" in [e.code for e in result.errors]) is over
    assert Path(result.artifacts["bom_json"]).exists()


def test_no_budget_is_never_over(tmp_path):
    result = price_bom(spec(budget_usd=None), LIB, tmp_path / "none.json", tmp_path)
    assert result.ok and result.data["over_budget"] is False


def test_missing_price_is_a_warning(tmp_path):
    part = LIB.get("buzzer_passive").model_copy(update={"manual_price_usd": None})
    lib = load_library()
    lib.parts["buzzer_passive"] = part
    result = price_bom(spec(), lib, tmp_path / "none.json", tmp_path)
    buzzer = line(result, "buzzer_passive")
    assert (buzzer.price_source, buzzer.unit_price_usd, buzzer.line_total_usd) == (
        "missing",
        None,
        0.0,
    )
    assert [(e.code, e.severity) for e in result.errors] == [
        ("price_missing", "warning")
    ]


def test_bom_json_matches_data_and_is_deterministic(cache, tmp_path):
    first = price_bom(spec(), LIB, cache, tmp_path / "a")
    second = price_bom(spec(), LIB, cache, tmp_path / "b")
    a, b = Path(first.artifacts["bom_json"]), Path(second.artifacts["bom_json"])
    assert a.parent == (tmp_path / "a").resolve()
    assert a.read_bytes() == b.read_bytes()
    assert json.loads(a.read_text()) == first.data
    assert [li["part_id"] for li in first.data["lines"]] == sorted(
        li["part_id"] for li in first.data["lines"]
    )


def test_unknown_part_is_an_error(tmp_path):
    s = spec()
    s = s.model_copy(
        update={"parts": [s.parts[0].model_copy(update={"part_id": "nope"})]}
    )
    result = price_bom(s, LIB, None, tmp_path)
    assert not result.ok and result.errors[0].code == "unknown_part"
