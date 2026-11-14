"""Project spec: the single source of truth for a run (docs/PROJECT_PLAN.md, "Project spec schema").

The agent fills `ProjectSpec`; every other artifact is generated from it by code. `Placement` and
`Layout` are computed by the layout tool, never by the model.
"""

from typing import Annotated, Literal

from pydantic import Field

from backend.contracts.base import Face, Model, Wall

Ref = Annotated[str, Field(pattern=r"^[a-z][a-z0-9]*$")]
"""Part reference such as "oled1": lowercase letters and digits only, because it becomes part of the
firmware macro PIN_<REF>_<PIN>."""

Bus = Literal["i2c", "spi", "i2s", "uart", "gpio", "analog", "power"]


class UserContext(Model):
    budget_usd: float | None = None
    owned_part_ids: list[str] = []
    """From the inventory memory."""
    printer: str | None = None
    """Printer profile id, e.g. "generic"."""
    rejected: list[str] = []
    """Choices the user turned down before, e.g. "no buzzers", "smaller case"."""


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


class Cutout(Model):
    """An extra opening the user asked for. Openings for part features come from the library."""

    for_ref: str
    feature: str
    """e.g. "usb", "lens", "window", "button"."""
    face: Face


class EnclosureSpec(Model):
    template: Literal["box_lid"] = "box_lid"
    wall_mm: float = Field(2.0, ge=1.2, le=4.0)
    clearance_mm: float = Field(1.0, ge=0)
    cutouts: list[Cutout] = []
    extras: list[str] = []
    """Free-form CAD requests, e.g. "belt clip"."""


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
    mcu: PartInstance
    parts: list[PartInstance]
    connections: list[Connection]
    firmware: FirmwareSpec
    enclosure: EnclosureSpec = EnclosureSpec()


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
    """One per part mounted inside (`PartDef.mounting == "inside"`), sorted by ref."""
    cavity_mm: tuple[float, float, float]
    """Inside length (x), width (y) and height (z)."""
