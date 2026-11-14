# T38: BomLine.offers, every store offer for a part, cheapest first
What: in `backend/contracts/artifacts.py` add
```python
class BomOffer(Model):
    seller: str
    url: str | None = None
    unit_price_usd: float
    """At the line's buy quantity (largest price break at or below it)."""
    in_stock: bool | None = None
    """None when the seller didn't say (Nexar inventoryLevel -3 unknown, -4 RFQ, or an old cache)."""
```
and on `BomLine`:
```python
    offers: list[BomOffer] = []
    """Live or cached store offers, one per seller, cheapest first (ties by seller name). Empty for
    manual, missing and fake prices. unit_price_usd and vendor_url equal offers[0] when there are any."""
```
then `make types` so the frontend gets `BomOffer`.
Why: `price_bom` keeps only the cheapest offer and drops the seller, so the Where-to-buy panel and
Buy all (T36 placeholders, connected by B-web) have nothing to show. The current contract has no
place for more than one store per line.
Affects: T38 (pricing.py fills it), B-web/T40 (connects Where to buy and Buy all after T38 merges).
No breaking change: the default `[]` keeps `fixtures/runs/plant_monitor/bom.json`, `fakes.py` and the
current UI valid, and `unit_price_usd`/`vendor_url` keep their meaning (the cheapest offer).
Optional: add 2-3 offers to the esp32_devkitc line of `fixtures/runs/plant_monitor/bom.json` so B-web
can build the panel against `P2D_RUNNER=fake`.
Workaround until decided: pricing.py computes the sorted offer list and uses offers[0] for
unit_price_usd/vendor_url; the `offers=` field is wired into `BomLine` after the contract lands.
