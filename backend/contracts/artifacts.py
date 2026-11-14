"""JSON files in a run directory that more than one task reads (the UI, cross_checks, the runtime)."""

from typing import Literal

from backend.contracts.base import Face, Model
from backend.contracts.events import Stage
from backend.contracts.parts import FeatureKind, PinType
from backend.contracts.spec import Bus


class ArtifactInfo(Model):
    path: str
    """Relative to the run directory."""
    stage: Stage
    spec_rev: int


class RunManifest(Model):
    """runs/<id>/manifest.json, written by the run engine from the events it records."""

    spec_rev: int
    """Rev of the current spec.json. Artifacts with an older spec_rev are stale."""
    artifacts: dict[str, ArtifactInfo]


class WiringRow(Model):
    part_ref: str
    part_name: str
    part_pin: str
    pin_type: PinType
    mcu_pin: str
    bus: Bus
    reason: str = ""


class Wiring(Model):
    """wiring.json: the spec's connections enriched with library names, for the wiring tab."""

    spec_rev: int
    rows: list[WiringRow]


class BomOffer(Model):
    seller: str
    url: str | None = None
    unit_price_usd: float
    """At the line's buy quantity (largest price break at or below it)."""
    in_stock: bool | None = None
    """None when the seller didn't say (Nexar inventoryLevel -3 unknown, -4 RFQ, or an old cache)."""


class BomLine(Model):
    part_id: str
    name: str
    refs: list[str]
    qty: int
    owned_qty: int = 0
    unit_price_usd: float | None
    line_total_usd: float
    """(qty - owned_qty) * unit price; 0 when fully owned or unpriced."""
    price_source: Literal["live", "cache", "manual", "fake", "missing"]
    vendor_url: str | None = None
    mpn: str | None = None
    offers: list[BomOffer] = []
    """Live or cached store offers, one per seller, cheapest first (ties by seller name). Empty for
    manual, missing and fake prices. unit_price_usd and vendor_url equal offers[0] when there are any."""


class Bom(Model):
    """bom.json, and the data of price_bom's ToolResult."""

    spec_rev: int
    lines: list[BomLine]
    total_usd: float
    budget_usd: float | None = None
    over_budget: bool
    prices_fetched_at: str | None = None
    """When the price cache was refreshed (ISO 8601), if any line came from it."""


class CutoutRecord(Model):
    for_ref: str
    feature: FeatureKind
    face: Face
    center_mm: tuple[float, float]
    """Face-plane (u, v) in the enclosure frame (see base.py)."""
    size_mm: tuple[float, float]


class EnclosureManifest(Model):
    """cad/manifest.json, written by build_enclosure: which opening serves which part feature."""

    spec_rev: int
    template: Literal["box_lid"] = "box_lid"
    wall_mm: float
    cavity_mm: tuple[float, float, float]
    outer_mm: tuple[float, float, float]
    """Outside size of the closed box, lid included."""
    cutouts: list[CutoutRecord]
    unmeasured_refs: list[str] = []
    """Parts whose dims_source isn't "measured": the UI says "verify before printing"."""
