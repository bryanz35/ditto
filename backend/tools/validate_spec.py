"""Spec validator (T10): checks a ProjectSpec against the parts library before anything is built.

Every board fact (pin names and types, rails, reserved, input-only, strapping and ADC pins, logic
voltage, power budget) comes from the board's library YAML; none is written here. Messages are read
by the parts sub-agent, so each names the part, pin and value and lists free alternatives.

Error codes (severity "error" unless noted):
- invalid_spec: the spec no longer matches the ProjectSpec model (re-validated here).
- unknown_part: a part_id isn't in the library, or the mcu's part_id isn't a board.
- duplicate_ref: two instances share a ref.
- unknown_ref: a connection names a ref that isn't one of the spec's parts.
- unknown_pin: a connection names a pin the part or the board doesn't have.
- pin_conflict: two part pins on one board pin (only I2C/SPI bus lines of one type may share), or
  one part pin wired to two board pins.
- reserved_pin: a board pin from `reserved_pins` is used.
- input_only_output: a pin the MCU drives is on one of `input_only_pins`.
- strapping_pin (warning): a pin the MCU drives is on one of `strapping_pins`.
- adc2_wifi: an analog read on one of `adc2_pins` while `firmware.needs_wifi`.
- not_adc_pin: an analog read on a pin in neither ADC list.
- pin_type_mismatch: supply or ground pin on a signal pin, or a signal on a rail.
- voltage_mismatch: a supply pin on a rail the part doesn't accept, or part logic above the board's.
- unconnected_pin: a required part pin has no connection.
- i2c_address_invalid: an address the part can't use, or address-pin wiring that selects another.
- i2c_address_conflict: two parts on one I2C bus at the same address.
- power_budget: the parts' total max current is above the board's `power_budget_ma`.
"""

from collections import Counter, defaultdict
from difflib import get_close_matches

from pydantic import ValidationError

from backend.contracts.parts import BoardDef, PartDef, PartLibrary, PinDef, PinType
from backend.contracts.results import ToolError, ToolResult
from backend.contracts.spec import Connection, PartInstance, ProjectSpec

RAILS = ("power", "gnd")
SHARED_BUS = {"i2c_sda", "i2c_scl", "spi_sck", "spi_mosi", "spi_miso"}
MCU_READS = {"gpio_in", "analog", "spi_miso", "uart_rx", "i2s_din"}
"""Pin types the MCU only reads; every other signal type is driven by the MCU (at least sometimes)."""


def validate_spec(spec: ProjectSpec, lib: PartLibrary) -> ToolResult:
    try:
        spec = ProjectSpec.model_validate(spec.model_dump(warnings=False))
    except ValidationError as e:
        return _result(
            [
                ToolError(
                    code="invalid_spec",
                    message=f"{_path(err['loc'])}: {err['msg']}",
                    field=_path(err["loc"]),
                )
                for err in e.errors()
            ]
        )
    return _result(_Check(spec, lib).run())


def _result(errors: list[ToolError]) -> ToolResult:
    return ToolResult(ok=not any(e.severity == "error" for e in errors), errors=errors)


def _path(loc: tuple) -> str:
    return "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in loc).lstrip(".")


def _kind(t: PinType) -> str:
    return "analog" if t == "analog" else "input" if t in MCU_READS else "output"


def _volts(vs: list[float]) -> str:
    return " or ".join(f"{v:g} V" for v in vs)


class _Check:
    def __init__(self, spec: ProjectSpec, lib: PartLibrary):
        self.spec, self.lib = spec, lib
        self.errors: list[ToolError] = []

    def add(self, code: str, message: str, field: str, severity: str = "error") -> None:
        self.errors.append(
            ToolError(code=code, message=message, field=field, severity=severity)
        )

    def run(self) -> list[ToolError]:
        spec, lib = self.spec, self.lib
        board = lib.parts.get(spec.mcu.part_id)
        if not isinstance(board, BoardDef):
            boards = ", ".join(
                sorted(p.id for p in lib.parts.values() if isinstance(p, BoardDef))
            )
            why = (
                "isn't in the library"
                if board is None
                else f"is a {board.category}, not a board"
            )
            self.add(
                "unknown_part",
                f"mcu {spec.mcu.ref} uses part id {spec.mcu.part_id!r}, which {why}; boards: {boards}",
                "mcu.part_id",
            )
            return self.errors
        self.board = board
        self.bpins = {p.name: p for p in board.pins}
        self.used = {
            c.mcu_pin
            for c in spec.connections
            if c.mcu_pin in self.bpins and self.bpins[c.mcu_pin].type not in RAILS
        }

        self.known = self._parts()
        signals = self._connections()
        self._conflicts(signals)
        self._unconnected()
        self._i2c()
        self._power()
        return self.errors

    # ------------------------------------------------------------------ helpers

    def rails(self, t: str, volts: list[float] | None = None) -> list[str]:
        return [
            p.name
            for p in self.board.pins
            if p.type == t
            and (volts is None or (p.voltage or self.board.logic_voltage) in volts)
        ]

    def accepted(self, part: PartDef, pin: PinDef) -> list[float]:
        return (
            [pin.voltage]
            if pin.voltage is not None
            else part.supply_voltage or [part.logic_voltage]
        )

    def free(self, kind: str) -> str:
        b = self.board
        pins = [
            p.name
            for p in b.pins
            if p.type not in RAILS
            and p.name not in b.reserved_pins
            and p.name not in self.used
        ]
        if kind == "output":
            pins = [
                p
                for p in pins
                if p not in b.input_only_pins and p not in b.strapping_pins
            ]
        elif kind == "analog":
            adc = b.adc1_pins + ([] if self.spec.firmware.needs_wifi else b.adc2_pins)
            pins = [p for p in adc if p in pins]  # ADC1 first: keeps Wi-Fi possible
        return f"free {kind} pins: {', '.join(pins) or 'none'}"

    def suggest(self, part: PartDef, pin: PinDef) -> str:
        """Where this part pin could go, as text for a message."""
        if pin.type == "power":
            return (
                " or ".join(self.rails("power", self.accepted(part, pin)))
                or f"a {_volts(self.accepted(part, pin))} rail (the board has none)"
            )
        if pin.type == "gnd":
            return " or ".join(self.rails("gnd"))
        if pin.type == "config":
            return " or ".join(self.rails("power") + self.rails("gnd"))
        if pin.type in SHARED_BUS:
            for c in self.spec.connections:
                p = self.known_by_ref.get(c.part_ref)
                if (
                    p
                    and self.lib.pin_type(p.id, c.part_pin) == pin.type
                    and c.mcu_pin in self.bpins
                ):
                    return f"{c.mcu_pin} (the bus line {c.part_ref}.{c.part_pin} already uses)"
        return self.free(_kind(pin.type))

    # ------------------------------------------------------------------ checks

    def _parts(self) -> list[tuple[int, PartInstance, PartDef]]:
        known, refs = [], {self.spec.mcu.ref}
        parts = sorted(
            p.id for p in self.lib.parts.values() if not isinstance(p, BoardDef)
        )
        for i, inst in enumerate(self.spec.parts):
            if inst.ref in refs:
                self.add(
                    "duplicate_ref",
                    f"ref {inst.ref!r} is used twice; give parts[{i}] ({inst.part_id}) its own ref (refs in use: {', '.join(sorted(refs))})",
                    f"parts[{i}].ref",
                )
                continue
            refs.add(inst.ref)
            if inst.part_id not in self.lib:
                near = get_close_matches(inst.part_id, parts, n=3, cutoff=0.5)
                hint = (
                    f"did you mean {' or '.join(near)}?"
                    if near
                    else f"library parts: {', '.join(parts)}"
                )
                self.add(
                    "unknown_part",
                    f"{inst.ref} uses part id {inst.part_id!r}, which isn't in the parts library; {hint}",
                    f"parts[{i}].part_id",
                )
                continue
            known.append((i, inst, self.lib.get(inst.part_id)))
        self.all_refs = refs - {self.spec.mcu.ref}
        self.known_by_ref = {inst.ref: part for _, inst, part in known}
        return known

    def _connections(self) -> list[tuple[int, Connection, PinDef]]:
        """Per-connection checks. Returns the valid signal (non-rail) connections."""
        b, signals = self.board, []
        for i, c in enumerate(self.spec.connections):
            at, where = f"connections[{i}]", f"{c.part_ref}.{c.part_pin}"
            if c.part_ref not in self.all_refs:
                why = (
                    f"{c.part_ref} is the board; connections go from a part to the board"
                    if c.part_ref == self.spec.mcu.ref
                    else f"no part has ref {c.part_ref!r}"
                )
                self.add(
                    "unknown_ref",
                    f"{at} wires {where}, but {why}; part refs: {', '.join(sorted(self.all_refs))}",
                    f"{at}.part_ref",
                )
                continue
            part = self.known_by_ref.get(c.part_ref)
            if part is None:  # unknown part id: already reported
                continue
            pin = next((p for p in part.pins if p.name == c.part_pin), None)
            if pin is None:
                self.add(
                    "unknown_pin",
                    f"{c.part_ref} ({part.id}) has no pin {c.part_pin!r}; its pins: {', '.join(p.name for p in part.pins)}",
                    f"{at}.part_pin",
                )
                continue
            bpin = self.bpins.get(c.mcu_pin)
            if bpin is None:
                self.add(
                    "unknown_pin",
                    f"{b.id} has no pin {c.mcu_pin!r} (wired to {where}); use {self.suggest(part, pin)}",
                    f"{at}.mcu_pin",
                )
                continue
            field = f"{at}.mcu_pin"

            if pin.type in RAILS or bpin.type in RAILS:
                if pin.type == "power" and bpin.type == "power":
                    rail, ok = bpin.voltage or b.logic_voltage, self.accepted(part, pin)
                    if rail not in ok:
                        self.add(
                            "voltage_mismatch",
                            f"{where} ({part.id}) accepts {_volts(ok)} but is wired to {c.mcu_pin} ({rail:g} V); wire it to {self.suggest(part, pin)}",
                            field,
                        )
                elif pin.type != bpin.type and not (
                    pin.type == "config" and bpin.type in RAILS
                ):
                    self.add(
                        "pin_type_mismatch",
                        f"{where} is a {pin.type} pin but is wired to {c.mcu_pin} ({bpin.type}); wire it to {self.suggest(part, pin)}",
                        field,
                    )
                continue

            signals.append((i, c, pin))
            kind = _kind(pin.type)
            if c.mcu_pin in b.reserved_pins:
                self.add(
                    "reserved_pin",
                    f"{c.mcu_pin} is reserved on {b.id} (flash or USB serial) but is wired to {where}; {self.suggest(part, pin)}",
                    field,
                )
                continue
            if kind == "output" and c.mcu_pin in b.input_only_pins:
                self.add(
                    "input_only_output",
                    f"{c.mcu_pin} is input-only on {b.id} but drives {where} ({pin.type}); {self.free('output')}",
                    field,
                )
                continue
            if kind == "analog":
                if c.mcu_pin in b.adc2_pins and self.spec.firmware.needs_wifi:
                    self.add(
                        "adc2_wifi",
                        f"{where} is an analog read on {c.mcu_pin}, an ADC2 pin, which fails while Wi-Fi is on (firmware.needs_wifi); {self.free('analog')}",
                        field,
                    )
                elif c.mcu_pin not in b.adc1_pins + b.adc2_pins:
                    self.add(
                        "not_adc_pin",
                        f"{where} is an analog read but {c.mcu_pin} has no ADC on {b.id}; {self.free('analog')}",
                        field,
                    )
            if part.logic_voltage > b.logic_voltage:
                self.add(
                    "voltage_mismatch",
                    f"{where} uses {part.logic_voltage:g} V logic but {c.mcu_pin} on {b.id} is {b.logic_voltage:g} V and can be damaged; pick a {b.logic_voltage:g} V-logic part for {c.part_ref}",
                    field,
                )
            if kind == "output" and c.mcu_pin in b.strapping_pins:
                self.add(
                    "strapping_pin",
                    f"{c.mcu_pin} is a strapping pin on {b.id}; driving {where} from it can stop the board booting; {self.free('output')}",
                    field,
                    "warning",
                )
        return signals

    def _conflicts(self, signals: list[tuple[int, Connection, PinDef]]) -> None:
        by_mcu: dict[str, list[tuple[int, Connection, PinDef]]] = defaultdict(list)
        by_part: dict[tuple[str, str], list[tuple[int, Connection]]] = defaultdict(list)
        for i, c, pin in signals:
            by_mcu[c.mcu_pin].append((i, c, pin))
            by_part[(c.part_ref, c.part_pin)].append((i, c))
        for mcu_pin, users in by_mcu.items():
            types = Counter(pin.type for _, _, pin in users)
            if len(users) < 2 or (len(types) == 1 and next(iter(types)) in SHARED_BUS):
                continue
            keep = types.most_common(1)[0][0]
            # Move the odd ones out; if all are one unshareable type, keep the first.
            movers = (
                [u for u in users if u[2].type != keep] if len(types) > 1 else users[1:]
            )
            listed = ", ".join(
                f"{c.part_ref}.{c.part_pin} ({pin.type})" for _, c, pin in users
            )
            for i, c, pin in movers:
                part = self.known_by_ref[c.part_ref]
                self.add(
                    "pin_conflict",
                    f"{mcu_pin} is used by {listed}; only I2C or SPI bus lines of the same kind may share a pin. Move {c.part_ref}.{c.part_pin} to one of the {self.suggest(part, pin)}",
                    f"connections[{i}].mcu_pin",
                )
        for (ref, pin_name), wires in by_part.items():
            for i, c in wires[1:]:
                self.add(
                    "pin_conflict",
                    f"{ref}.{pin_name} is wired to both {wires[0][1].mcu_pin} and {c.mcu_pin}; keep one connection",
                    f"connections[{i}]",
                )

    def _unconnected(self) -> None:
        wired = {(c.part_ref, c.part_pin) for c in self.spec.connections}
        for i, inst, part in self.known:
            for pin in part.pins:
                if not pin.optional and (inst.ref, pin.name) not in wired:
                    self.add(
                        "unconnected_pin",
                        f"{inst.ref}.{pin.name} ({part.id}, {pin.type}) isn't wired; connect it to {self.suggest(part, pin)}",
                        f"parts[{i}]",
                    )

    def _i2c(self) -> None:
        buses: dict[str, list[tuple[int, PartInstance, PartDef, str]]] = defaultdict(
            list
        )
        for i, inst, part in self.known:
            field = f"parts[{i}].i2c_address"
            if not part.i2c_addresses:
                if inst.i2c_address:
                    self.add(
                        "i2c_address_invalid",
                        f"{inst.ref} ({part.id}) isn't an I2C part; set its i2c_address to null",
                        field,
                    )
                continue
            addr = inst.i2c_address or part.i2c_addresses[0]
            if addr not in part.i2c_addresses:
                self.add(
                    "i2c_address_invalid",
                    f"{inst.ref} uses I2C address {addr}, but {part.id} supports only {', '.join(part.i2c_addresses)}",
                    field,
                )
                continue
            sel = part.i2c_address_pin
            if sel and len(part.i2c_addresses) > 1:
                high = any(
                    c.part_ref == inst.ref
                    and c.part_pin == sel
                    and self.bpins.get(c.mcu_pin, None)
                    and self.bpins[c.mcu_pin].type == "power"
                    for c in self.spec.connections
                )
                picked = part.i2c_addresses[1 if high else 0]
                if picked != addr:
                    rail = (
                        " or ".join(self.rails("power", [part.logic_voltage]))
                        or "the logic rail"
                    )
                    fix = (
                        f"wire {inst.ref}.{sel} to {rail}"
                        if addr == part.i2c_addresses[1]
                        else f"disconnect {inst.ref}.{sel} from {rail}"
                    )
                    self.add(
                        "i2c_address_invalid",
                        f"{inst.ref}.i2c_address is {addr}, but {inst.ref}.{sel} {'is' if high else 'is not'} wired to the supply rail, which selects {picked}; {fix}, or set i2c_address to {picked}",
                        field,
                    )
                    continue
            sda = next(
                (
                    c.mcu_pin
                    for c in self.spec.connections
                    if c.part_ref == inst.ref
                    and self.lib.pin_type(part.id, c.part_pin) == "i2c_sda"
                ),
                None,
            )
            if sda:
                buses[sda].append((i, inst, part, addr))
        for sda, members in buses.items():
            taken: dict[str, str] = {}
            in_use = {a for *_, a in members}
            for i, inst, part, addr in members:
                if addr not in taken:
                    taken[addr] = inst.ref
                    continue
                alts = [a for a in part.i2c_addresses if a not in in_use]
                if not alts:
                    fix = f"{part.id} has no other free address on this bus ({', '.join(part.i2c_addresses)} are taken); remove {inst.ref} or move it to a second I2C bus"
                elif part.i2c_address_pin and alts[0] == part.i2c_addresses[1]:
                    fix = f"set {inst.ref}.i2c_address to {alts[0]} and wire {inst.ref}.{part.i2c_address_pin} to {' or '.join(self.rails('power', [part.logic_voltage]))}"
                else:
                    fix = f"set {inst.ref}.i2c_address to {alts[0]} (and set the module's address jumper to match)"
                self.add(
                    "i2c_address_conflict",
                    f"{inst.ref} and {taken[addr]} both use I2C address {addr} on the bus at {sda}; {fix}",
                    f"parts[{i}].i2c_address",
                )

    def _power(self) -> None:
        # shortcut: counts every part against the board regulator, even parts on a 5 V rail; split by
        # rail if 5 V-heavy parts (servos, LED strips) start raising false alarms.
        draws = sorted(
            ((part.max_current_ma, inst.ref) for _, inst, part in self.known),
            reverse=True,
        )
        total, budget = sum(ma for ma, _ in draws), self.board.power_budget_ma
        if total > budget:
            listed = ", ".join(f"{ref} {ma:g} mA" for ma, ref in draws)
            self.add(
                "power_budget",
                f"the parts draw up to {total:g} mA but {self.board.id} can supply {budget:g} mA to attached parts ({listed}); drop or swap the biggest consumers, or give them their own supply",
                "parts",
            )
