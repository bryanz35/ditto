"""Refresh backend/parts/prices.json from Nexar for every library part with an MPN (T16).

Run before the event (needs NEXAR_CLIENT_ID and NEXAR_CLIENT_SECRET; one query per run):
    uv run --env-file .env python scripts/prefetch_prices.py [--out PATH]
"""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.contracts.parts import load_library
from backend.tools.pricing import PRICES_FILE, TIMEOUT_S, fetch_offers


def prefetch(out: Path, client_id: str, client_secret: str) -> dict:
    mpns = sorted({p.mpn for p in load_library().parts.values() if p.mpn})
    with httpx.Client(timeout=TIMEOUT_S) as http:
        parts = fetch_offers(mpns, client_id, client_secret, http)
    cache = {
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "currency": "USD",
        "parts": parts,
    }
    out.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")
    return cache


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=PRICES_FILE)
    args = parser.parse_args()
    client_id, secret = (
        os.environ.get("NEXAR_CLIENT_ID"),
        os.environ.get("NEXAR_CLIENT_SECRET"),
    )
    if not (client_id and secret):
        print("Set NEXAR_CLIENT_ID and NEXAR_CLIENT_SECRET (see .env.example).")
        return 1
    cache = prefetch(args.out, client_id, secret)
    print(f"Wrote {len(cache['parts'])} MPNs to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
