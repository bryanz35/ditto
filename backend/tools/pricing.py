"""BOM pricing with the Nexar API and a JSON cache (T16).

Each line's unit price comes from, in order: a live Nexar lookup (only when NEXAR_CLIENT_ID and
NEXAR_CLIENT_SECRET are set and the part has an MPN), the price cache (backend/parts/prices.json,
written by scripts/prefetch_prices.py), the library's manual_price_usd, else it is "missing".
Owned parts (spec.user.owned) cost nothing. price_bom never writes the cache.

Cache file: {"fetched_at": ISO 8601, "currency": "USD", "parts": {mpn: [offer, ...]}}, where an offer
is {"seller": str, "url": str | null, "breaks": [[min_qty, unit_price_usd], ...]} sorted by min_qty.

Error codes:
- over_budget (error): the total is above spec.user.budget_usd; bom.json is still written.
- price_missing (warning): no live, cached or manual price for a part; its line counts as $0.
- live_prices_unavailable (warning): the Nexar lookup failed (auth, rate limit, timeout, bad reply);
  cached and manual prices were used instead.
"""

import json
import os
from pathlib import Path

import httpx

from backend.contracts.artifacts import Bom, BomLine
from backend.contracts.parts import PARTS_DIR, PartLibrary
from backend.contracts.results import ToolError, ToolResult
from backend.contracts.spec import ProjectSpec

PRICES_FILE = PARTS_DIR / "prices.json"
TOKEN_URL = "https://identity.nexar.com/connect/token"
GRAPHQL_URL = "https://api.nexar.com/graphql"
TIMEOUT_S = 10.0

# Field names from Nexar's own example (NexarDeveloper/nexar-examples-py, mpn_pricing_to_csv.py).
QUERY = """
query ($queries: [SupPartMatchQuery!]!) {
  supMultiMatch(currency: "USD", queries: $queries) {
    parts {
      mpn
      sellers {
        company { name }
        offers { clickUrl prices { quantity price currency } }
      }
    }
  }
}
"""


def fetch_offers(
    mpns: list[str], client_id: str, client_secret: str, http: httpx.Client
) -> dict[str, list[dict]]:
    """MPN -> offers with USD price breaks, from one supMultiMatch call. Raises httpx.HTTPError
    (401, 429, timeouts) or ValueError (GraphQL errors, unexpected reply) for the caller."""
    token = http.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    token.raise_for_status()
    reply = http.post(
        GRAPHQL_URL,
        json={
            "query": QUERY,
            "variables": {"queries": [{"mpn": m, "limit": 1} for m in mpns]},
        },
        headers={"token": token.json()["access_token"]},
    )
    reply.raise_for_status()
    body = reply.json()
    if body.get("errors") or not isinstance(body.get("data"), dict):
        raise ValueError(f"Nexar replied with errors: {body.get('errors')}")
    offers: dict[str, list[dict]] = {}
    # One match per query, in query order; key by our MPN, not Nexar's spelling of it.
    for mpn, match in zip(mpns, body["data"]["supMultiMatch"]):
        for part in match["parts"]:
            for seller in part["sellers"]:
                for offer in seller["offers"]:
                    breaks = sorted(
                        [p["quantity"], p["price"]]
                        for p in offer["prices"]
                        if p["currency"] == "USD"
                    )
                    if breaks:
                        offers.setdefault(mpn, []).append(
                            {
                                "seller": seller["company"]["name"],
                                "url": offer.get("clickUrl"),
                                "breaks": breaks,
                            }
                        )
    return offers


def best_offer(offers: list[dict], qty: int) -> tuple[float, str | None] | None:
    """Cheapest (unit price, url) when buying qty: each offer's largest break at or below qty."""
    best = None
    for offer in offers:
        breaks = offer["breaks"]
        # shortcut: below the smallest break (MOQ) we still use its unit price; fine for hobby qty.
        price = next((p for q, p in reversed(breaks) if q <= qty), breaks[0][1])
        if best is None or price < best[0]:
            best = (price, offer.get("url"))
    return best


def _live_offers(mpns: list[str]) -> tuple[dict[str, list[dict]], list[ToolError]]:
    client_id, secret = (
        os.environ.get("NEXAR_CLIENT_ID"),
        os.environ.get("NEXAR_CLIENT_SECRET"),
    )
    if not (mpns and client_id and secret):
        return {}, []
    try:
        with httpx.Client(timeout=TIMEOUT_S) as http:
            return fetch_offers(mpns, client_id, secret, http), []
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
        return {}, [
            ToolError(
                code="live_prices_unavailable",
                message=f"Nexar price lookup failed ({type(e).__name__}: {e}); "
                "used cached and manual prices instead.",
                severity="warning",
            )
        ]


def _load_cache(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {}


def price_bom(
    spec: ProjectSpec, lib: PartLibrary, prices: Path | None, out_dir: Path
) -> ToolResult:
    groups: dict[str, list] = {}
    for inst in [spec.mcu, *spec.parts]:
        groups.setdefault(inst.part_id, []).append(inst)
    unknown = sorted(pid for pid in groups if pid not in lib)
    if unknown:
        return ToolResult(
            ok=False,
            errors=[
                ToolError(
                    code="unknown_part",
                    message=f"Parts not in the library: {', '.join(unknown)}. "
                    "Use library part ids only.",
                    field="parts",
                )
            ],
        )

    mpns = sorted({lib.get(pid).mpn for pid in groups} - {None})
    live, errors = _live_offers(mpns)
    cache = _load_cache(prices or PRICES_FILE)
    cached = cache.get("parts", {})

    lines, used_cache = [], False
    for pid in sorted(groups):
        part, insts = lib.get(pid), groups[pid]
        qty = sum(i.qty for i in insts)
        owned = min(spec.user.owned.get(pid, 0), qty)
        buy = max(qty - owned, 1)  # fully owned lines still show what one would cost
        source, unit, url = "missing", None, part.vendor_url
        if part.mpn in live and (hit := best_offer(live[part.mpn], buy)):
            source, (unit, url) = "live", hit
        elif part.mpn in cached and (hit := best_offer(cached[part.mpn], buy)):
            source, (unit, url), used_cache = "cache", hit, True
        elif part.manual_price_usd is not None:
            source, unit = "manual", part.manual_price_usd
        else:
            errors.append(
                ToolError(
                    code="price_missing",
                    message=f"No price for {pid} ({part.name}): no MPN match, cache entry or "
                    "manual_price_usd. Its line counts as $0.",
                    severity="warning",
                )
            )
        lines.append(
            BomLine(
                part_id=pid,
                name=part.name,
                refs=sorted(i.ref for i in insts),
                qty=qty,
                owned_qty=owned,
                unit_price_usd=unit,
                line_total_usd=round((qty - owned) * (unit or 0.0), 2),
                price_source=source,
                vendor_url=url or part.vendor_url,
                mpn=part.mpn,
            )
        )

    total = round(sum(line.line_total_usd for line in lines), 2)
    budget = spec.user.budget_usd
    bom = Bom(
        spec_rev=spec.rev,
        lines=lines,
        total_usd=total,
        budget_usd=budget,
        over_budget=budget is not None and total > budget,
        prices_fetched_at=cache.get("fetched_at") if used_cache else None,
    )
    if bom.over_budget:
        costly = sorted(lines, key=lambda line: -line.line_total_usd)[:3]
        errors.append(
            ToolError(
                code="over_budget",
                message=f"BOM total ${total:.2f} is ${total - budget:.2f} over the "
                f"${budget:.2f} budget. Biggest lines: "
                + ", ".join(f"{li.part_id} ${li.line_total_usd:.2f}" for li in costly)
                + ".",
                field="user.budget_usd",
                hint="Swap in cheaper library parts or owned ones, drop optional parts, "
                "or ask the user to approve the higher total.",
            )
        )

    out = Path(out_dir) / "bom.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(bom.model_dump_json(indent=2) + "\n")
    return ToolResult(
        ok=not bom.over_budget,
        errors=errors,
        artifacts={"bom_json": str(out.resolve())},
        data=bom.model_dump(mode="json"),
    )
