"""Parts library: one hand-checked YAML file per part in backend/parts/library/ (docs/PROJECT_PLAN.md,
"Parts library"). Board facts live in the board's YAML, never in code."""

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import Field, ValidationError, model_validator

from backend.contracts.base import Face, Model

PARTS_DIR = Path(__file__).resolve().parents[1] / "parts"
LIBRARY_DIR = PARTS_DIR / "library"

PinType = Literal[
    "power",
    "gnd",
    "gpio",
    "gpio_in",
    "gpio_out",
    "analog",
    "i2c_sda",
    "i2c_scl",
    "spi_sck",
    "spi_mosi",
    "spi_miso",
    "spi_cs",
    "uart_tx",
    "uart_rx",
    "i2s_bclk",
    "i2s_ws",
    "i2s_din",
    "i2s_dout",
    "config",
]
"""Signal directions are seen from the MCU: gpio_out means the MCU drives the pin (buzzer SIG,
HC-SR04 TRIG), gpio_in means the MCU reads it (button, PIR OUT), uart_tx goes to the part's RX,
i2s_din carries data into the MCU (microphone SD). "gpio" is a bidirectional board header pin.
"config" is a strap or select pin tied to 3V3 or GND (I2C address select, mic L/R channel)."""

Category = Literal["mcu", "sensor", "display", "light", "input", "output", "power"]
FeatureKind = Literal[
    "usb", "display_window", "lens", "button", "led", "sound", "vent", "cable"
]
PinName = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_]*$")]
I2cAddress = Annotated[str, Field(pattern=r"^0x[0-9A-F]{2}$")]


class PinDef(Model):
    name: PinName
    """As printed on the module; becomes part of PIN_<REF>_<PIN>, so no spaces or slashes."""
    type: PinType
    voltage: float | None = None
    """Rail voltage for power pins; None means the part's logic_voltage."""
    optional: bool = False
    """May be left unconnected (e.g. an address-select pin with an on-board pull-down)."""


class Dims(Model):
    l: float = Field(gt=0)
    w: float = Field(gt=0)
    h: float = Field(gt=0)
    """Overall height, including pin headers and the tallest component."""


class MountHole(Model):
    x_mm: float
    y_mm: float
    d_mm: float = Field(gt=0)


class Feature(Model):
    """Something on the part that needs an opening in the enclosure (part frame, see base.py)."""

    kind: FeatureKind
    face: Face
    """The face of the part it points out of."""
    offset_mm: tuple[float, float]
    """Centre of the feature in face-plane coordinates (u, v) from the part's origin."""
    size_mm: tuple[float, float]
    """Opening width and height along (u, v)."""


class PartDef(Model):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    """Equals the YAML file name."""
    name: str
    category: Category
    pins: list[PinDef]
    logic_voltage: float
    supply_voltage: list[float]
    """Supply rails the part accepts, e.g. [3.3, 5.0]."""
    max_current_ma: float = Field(ge=0)
    i2c_addresses: list[I2cAddress] = []
    """First is the default; the rest are selectable on the module."""
    board_mm: Dims
    mounting: Literal["inside", "external"] = "inside"
    """external: sits outside the case (soil probe, servo arm); the enclosure gets a cable hole
    instead of a placement."""
    mount_holes: list[MountHole] = []
    features: list[Feature] = []
    provisional: bool = True
    """True until a human has measured the part with calipers."""
    dims_source: Literal["measured", "datasheet", "listing"]
    pio_lib_deps: list[str] = []
    snippet: str | None = None
    """Known-good example program, relative to backend/parts/ (e.g. "snippets/<id>.cpp")."""
    mpn: str | None = None
    vendor_url: str | None = None
    manual_price_usd: float | None = None
    owned_alternatives: list[str] = []
    """Part ids that can stand in for this one."""
    wokwi_type: str | None = None
    """Wokwi part type; None when Wokwi doesn't have the part."""
    wokwi_pins: dict[str, str] = {}
    """Our pin name -> Wokwi pin name, where they differ."""
    wokwi_attrs: dict[str, str] = {}
    source: str
    """Datasheet or vendor URL for the pins, voltages and addresses."""

    @model_validator(mode="after")
    def _check_pins(self):
        names = [p.name for p in self.pins]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate pin names in {names}")
        unknown = set(self.wokwi_pins) - set(names)
        if unknown:
            raise ValueError(f"wokwi_pins names unknown pins {sorted(unknown)}")
        return self


class BoardDef(PartDef):
    """A microcontroller board: load_library uses this model for files with category "mcu"."""

    pio_board: str
    """PlatformIO board id, e.g. "esp32dev"."""
    wokwi_board: str | None = None
    reserved_pins: list[str]
    """Never usable (flash, USB serial)."""
    input_only_pins: list[str]
    strapping_pins: list[str]
    """Usable, but outputs here can break boot: warn."""
    adc1_pins: list[str]
    adc2_pins: list[str]
    """Analog reads here fail while Wi-Fi is on."""
    power_budget_ma: float = Field(gt=0)
    """Current the board's regulator can give the attached parts."""

    @model_validator(mode="after")
    def _check_pin_lists(self):
        names = {p.name for p in self.pins}
        for field in (
            "reserved_pins",
            "input_only_pins",
            "strapping_pins",
            "adc1_pins",
            "adc2_pins",
        ):
            unknown = set(getattr(self, field)) - names
            if unknown:
                raise ValueError(
                    f"{field} names pins the board doesn't have: {sorted(unknown)}"
                )
        return self


class PartLibrary:
    def __init__(self, parts: dict[str, PartDef]):
        self.parts = parts

    def __contains__(self, part_id: object) -> bool:
        return part_id in self.parts

    def get(self, part_id: str) -> PartDef:
        """Raises KeyError for unknown ids: check `part_id in lib` first."""
        return self.parts[part_id]

    def pin_type(self, part_id: str, pin: str) -> PinType | None:
        """Type of one pin, or None if the part or pin doesn't exist."""
        part = self.parts.get(part_id)
        return (
            next((p.type for p in part.pins if p.name == pin), None) if part else None
        )


def load_library(directory: Path = LIBRARY_DIR) -> PartLibrary:
    parts: dict[str, PartDef] = {}
    for path in sorted(directory.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text())
        model = BoardDef if raw.get("category") == "mcu" else PartDef
        try:
            part = model.model_validate(raw)
        except ValidationError as e:
            raise ValueError(f"{path.name}: {e}") from e
        if part.id != path.stem:
            raise ValueError(f"{path.name}: id {part.id!r} doesn't match the file name")
        parts[part.id] = part
    return PartLibrary(parts)
