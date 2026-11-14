"""Reads handoff/HARDWARE.md (filled in by the humans at H0): which demo mode we're in."""

import re
from pathlib import Path
from typing import Literal

from backend.contracts.base import Model

HARDWARE_FILE = Path(__file__).resolve().parents[2] / "handoff" / "HARDWARE.md"


class Hardware(Model):
    has_parts: bool | None
    """None while unknown."""
    has_printer: bool | None
    printer_model: str
    """Printer profile id in backend/parts/printers/."""
    mode: Literal["P", "E", "V"]
    """Unknown counts as V, the strictest mode."""
    simulate: bool
    """Whether the simulate stage runs (SIMULATE=auto: on in modes E and V, off in P)."""


def load_hardware(path: Path = HARDWARE_FILE) -> Hardware:
    values = dict(re.findall(r"^([A-Z_]+)=(\S*)", path.read_text(), re.MULTILINE))
    yes_no = {"yes": True, "no": False}
    mode = values.get("MODE", "").upper()
    mode = mode if mode in ("P", "E", "V") else "V"
    simulate = values.get("SIMULATE", "auto").lower()
    return Hardware(
        has_parts=yes_no.get(values.get("HAS_PARTS", "").lower()),
        has_printer=yes_no.get(values.get("HAS_PRINTER", "").lower()),
        printer_model=values.get("PRINTER_MODEL") or "generic",
        mode=mode,
        simulate=mode != "P" if simulate == "auto" else simulate == "on",
    )
