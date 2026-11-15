"""Project spec: the single source of truth for a run (docs/PROJECT_PLAN.md, "Project spec schema").

The agent fills `ProjectSpec`; every other artifact is generated from it by code. `Placement` and
`Layout` are computed by the layout tool, never by the model.

A project is a printed object, an electronics device, or both. A print-only project (a book holder)
has no `mcu`, `firmware`, `parts` or `connections`, and its shape comes from `enclosure.code`.
"""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from backend.contracts.base import I2cAddress, Model, Wall
from backend.contracts.parts import CUSTOM_PREFIX, BoardDef, PartDef, PartLibrary

Ref = Annotated[str, Field(pattern=r"^[a-z][a-z0-9]*$")]
"""Part reference such as "oled1": lowercase letters and digits only, because it becomes part of the
firmware macro PIN_<REF>_<PIN>."""

Bus = Literal["i2c", "spi", "i2s", "uart", "gpio", "analog", "power"]


class UserContext(Model):
    budget_usd: float | None = Field(None, ge=0)
    owned: dict[str, Annotated[int, Field(ge=0)]] = {}
    """Part id -> quantity on hand, from the inventory memory. The BOM prices only what's missing."""
    printer: str | None = None
    """Printer profile id, e.g. "generic". When None, use HARDWARE.md's PRINTER_MODEL."""
    rejected: list[str] = []
    """Choices the user turned down before, e.g. "no buzzers", "smaller case"."""
    level: Literal["beginner", "intermediate", "expert"] = "intermediate"
    """How much the agent explains: wording of reasons, assumptions and questions, and part choices."""
    name: str | None = None
    """Display name: shown in the sidebar; the agent addresses the user by it."""


class PartInstance(Model):
    ref: Ref
    """Unique in this spec, e.g. "oled1"."""
    part_id: str
    """Key into the parts library."""
    qty: int = Field(1, ge=1)
    """Use a separate ref for every part that gets wired; qty > 1 only for unwired extras."""
    role: str
    """What it does in this device, e.g. "shows soil moisture"."""
    reason: str
    """Explain mode: why this part was chosen."""
    i2c_address: I2cAddress | None = None
    """For I2C parts: the address this instance uses, one of PartDef.i2c_addresses (None = the
    first). If the part has an i2c_address_pin, its wiring must select this address."""
    mounting: Literal["inside", "external"] | None = None
    """Where this one sits, when not where the part usually does (PartDef.mounting): "external"
    for a sensor or camera on an arm, head or bracket, which gets a cable hole instead of a place
    in the case. None = the part's default. Never "external" for the mcu."""


def mounting(p: PartInstance, lib: PartLibrary) -> Literal["inside", "external"]:
    """Where a part instance sits: its own `mounting`, else the library part's."""
    return p.mounting or lib.get(p.part_id).mounting


class Connection(Model):
    part_ref: str
    """Ref of the part, e.g. "oled1"."""
    part_pin: str
    """Pin name from the part's library entry, e.g. "SDA"."""
    mcu_pin: str
    """Pin name from the board's library entry, e.g. "GPIO21", "3V3", "GND"."""
    bus: Bus
    reason: str = ""
    """Explain mode: why this pin."""


class EnclosureSpec(Model):
    """Openings come from the parts' library features (and a cable hole per external part).

    template "box_lid": a plain case from the fixed template. template "custom": `code` is build123d
    source written by the model (backend/tools/custom_model.py says what it must define); code runs
    it in a subprocess and checks every printed part."""

    template: Literal["box_lid", "custom"] = "box_lid"
    wall_mm: float = Field(2.0, ge=1.2, le=4.0)
    clearance_mm: float = Field(1.0, ge=0)
    extras: list[str] = []
    """Free-form CAD requests, e.g. "belt clip"."""
    code: str | None = None
    """build123d source for template "custom"; None for "box_lid"."""

    @model_validator(mode="after")
    def _code_matches_template(self):
        if (self.template == "custom") != bool(self.code):
            raise ValueError(
                'template "custom" needs `code` (build123d source), and "box_lid" takes none'
            )
        return self


class FirmwareSpec(Model):
    framework: Literal["arduino"] = "arduino"
    behaviors: list[str]
    """e.g. "every 10 min, read soil moisture and show it"."""
    needs_wifi: bool = False


class ProjectSpec(Model):
    rev: int = Field(0, ge=0)
    """Bumped by every saved change; each artifact records the rev it was built from."""
    title: str
    prompt: str
    requirements: list[str]
    """Restated, testable requirements."""
    assumptions: list[str] = []
    """Stated when we didn't ask."""
    user: UserContext = UserContext()
    mcu: PartInstance | None = None
    """The board; None for a print-only project (no electronics)."""
    parts: list[PartInstance] = []
    connections: list[Connection] = []
    firmware: FirmwareSpec | None = None
    """Set exactly when `mcu` is."""
    enclosure: EnclosureSpec = EnclosureSpec()
    custom_parts: list[PartDef] = []
    """Parts the library doesn't have, defined by the agent from a listing or datasheet (`source`).
    Ids start with "x_"; never a board; never "measured". Unverified: the UI says so, and the
    validator warns for each one used."""

    @model_validator(mode="after")
    def _electronics_go_together(self):
        if (self.mcu is None) != (self.firmware is None):
            raise ValueError(
                "mcu and firmware go together: set both for a device with electronics, or "
                "neither (null) for a print-only object"
            )
        if self.mcu is not None and self.mcu.mounting == "external":
            raise ValueError(
                'the mcu sits inside the case: leave its mounting unset; "external" is for '
                "parts on an arm, head or bracket"
            )
        if self.mcu is None and (self.parts or self.connections):
            raise ValueError(
                "parts and connections need an mcu; a print-only object has neither"
            )
        for p in self.custom_parts:
            if not p.id.startswith(CUSTOM_PREFIX):
                raise ValueError(
                    f"custom part id {p.id!r} must start with {CUSTOM_PREFIX!r}, e.g. "
                    f"{CUSTOM_PREFIX}{p.id}"
                )
            if p.category == "mcu" or isinstance(p, BoardDef):
                raise ValueError(
                    f"custom part {p.id!r} is a board; boards come from the library only"
                )
            if p.dims_source == "measured":
                raise ValueError(
                    f'custom part {p.id!r}: nobody measured it, so dims_source is "listing" '
                    'or "datasheet"'
                )
        ids = [p.id for p in self.custom_parts]
        if len(ids) != len(set(ids)):
            raise ValueError(f"custom_parts ids repeat: {sorted(ids)}")
        return self

    @property
    def instances(self) -> list[PartInstance]:
        """Every part instance, the board first; empty for a print-only project."""
        return [self.mcu, *self.parts] if self.mcu else []


class Placement(Model):
    """Where the layout put one part inside the cavity (enclosure frame, see base.py)."""

    ref: Ref
    x_mm: float
    """Left edge of the part's footprint after rotation, measured from the left wall."""
    y_mm: float
    """Front edge of the part's footprint after rotation, measured from the front wall."""
    z_mm: float = 0.0
    """Bottom of the part above the cavity floor (standoff height)."""
    rot_deg: Literal[0, 90, 180, 270] = 0
    """Rotation about the vertical axis, counter-clockwise seen from above."""
    against_wall: Wall | None = None
    """The wall this part touches because one of its features faces it."""


class Layout(Model):
    placements: list[Placement]
    """One per part mounted inside (`mounting(p, lib) == "inside"`), the mcu included, sorted by
    ref."""
    cavity_mm: tuple[float, float, float]
    """Inside length (x), width (y) and height (z)."""
