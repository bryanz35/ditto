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


class Pose(Model):
    """Where a custom device's extra printed part or mounted external part sits once assembled
    (written by build_custom_model)."""

    on: str
    """What it attaches to, put in before it: "base", "lid", an extra printed part's name or a
    mounted part's ref."""
    transform: list[float]
    """4x4 row-major, into the enclosure frame: for a printed part, from the part as exported (its
    print position); for a mounted part, from its box (x 0..l, y 0..w, z 0..h of its board_mm)."""


class EnclosureManifest(Model):
    """cad/manifest.json, written by build_enclosure or build_custom_model: which opening serves which
    part feature, and which parts get printed."""

    spec_rev: int
    template: Literal["box_lid", "custom"] = "box_lid"
    wall_mm: float
    cavity_mm: tuple[float, float, float]
    """(0, 0, 0) for a print-only project: there is no case."""
    outer_mm: tuple[float, float, float]
    """Outside size of the closed box, lid included; for a print-only project, of its biggest part."""
    cutouts: list[CutoutRecord]
    prints: dict[str, tuple[float, float, float]] = {}
    """Every printed part: name (its STL is cad/<name>.stl) -> bounding box size (x, y, z) as
    exported. "base" and "lid" for a device."""
    unmeasured_refs: list[str] = []
    """Parts whose dims_source isn't "measured": the UI says "verify before printing"."""
    assembled: dict[str, Pose] = {}
    """A custom device's extra printed parts, by name."""
    mounts: dict[str, Pose] = {}
    """External parts that a printed part holds (a servo in an arm link), by ref. The others sit
    beside the device."""
    build_order: list[str] = []
    """The names in `assembled` and refs in `mounts` in an order they can be put together: each
    after the part it attaches to."""
