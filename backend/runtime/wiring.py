"""build_wiring: wiring.json for the wiring tab (the spec's connections with library names).

Error codes:
- unknown_ref: a connection names a part_ref that isn't the mcu or a part in the spec.
- unknown_part: a part's part_id isn't in the library.
- unknown_pin: a connection names a pin the part's library entry doesn't have.
"""

from pathlib import Path

from backend.contracts.artifacts import Wiring, WiringRow
from backend.contracts.parts import PartLibrary
from backend.contracts.results import ToolError, ToolResult
from backend.contracts.spec import ProjectSpec


def build_wiring(spec: ProjectSpec, lib: PartLibrary, out_dir: Path) -> ToolResult:
    parts = {p.ref: p for p in [spec.mcu, *spec.parts]}
    rows, errors = [], []
    for i, c in enumerate(spec.connections):
        field = f"connections[{i}]"
        part = parts.get(c.part_ref)
        if part is None:
            refs = ", ".join(sorted(parts))
            errors.append(
                ToolError(
                    code="unknown_ref",
                    message=f"{field} names part {c.part_ref!r}, which isn't in the spec; refs: {refs}",
                    field=f"{field}.part_ref",
                )
            )
            continue
        if part.part_id not in lib:
            errors.append(
                ToolError(
                    code="unknown_part",
                    message=f"{c.part_ref} uses part {part.part_id!r}, which isn't in the library",
                    field=f"{field}.part_ref",
                )
            )
            continue
        pin_type = lib.pin_type(part.part_id, c.part_pin)
        if pin_type is None:
            pins = ", ".join(p.name for p in lib.get(part.part_id).pins)
            errors.append(
                ToolError(
                    code="unknown_pin",
                    message=f"{c.part_ref} ({part.part_id}) has no pin {c.part_pin!r}; pins: {pins}",
                    field=f"{field}.part_pin",
                )
            )
            continue
        rows.append(
            WiringRow(
                part_ref=c.part_ref,
                part_name=lib.get(part.part_id).name,
                part_pin=c.part_pin,
                pin_type=pin_type,
                mcu_pin=c.mcu_pin,
                bus=c.bus,
                reason=c.reason,
            )
        )
    if errors:
        return ToolResult(ok=False, errors=errors)
    wiring = Wiring(spec_rev=spec.rev, rows=rows)
    path = (Path(out_dir) / "wiring.json").resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(wiring.model_dump_json(indent=2) + "\n")
    return ToolResult(
        ok=True,
        artifacts={"wiring_json": str(path)},
        data=wiring.model_dump(mode="json"),
    )
