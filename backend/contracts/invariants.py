"""Invariants that must hold between the spec and every artifact generated from it.

Shared by the integration tests, the e2e tests and evals/run_evals.py (and T21 may reuse them). Each
check is a pure function returning a list of readable problems: empty means the invariant holds.
Written from backend/contracts/ and docs/PROJECT_PLAN.md ("Keeping the sub-tasks aligned"), not from
any implementation.
"""

import re
from itertools import combinations
from pathlib import Path

from backend.contracts.artifacts import Bom, EnclosureManifest, RunManifest, Wiring
from backend.contracts.events import Event
from backend.contracts.parts import PartLibrary, load_library, pin_code
from backend.contracts.spec import Layout, PartInstance, ProjectSpec, mounting

TOL = 0.01  # mm / USD: float slack for computed values
PIPELINE = (
    "validate",
    "layout",
    "enclosure",
    "assembly",
    "firmware",
    "wiring",
    "simulate",
    "bom",
)


def _instances(spec: ProjectSpec) -> list[PartInstance]:
    return spec.instances


def _known(spec: ProjectSpec, lib: PartLibrary) -> list[PartInstance]:
    """Instances whose part exists in the library (unknown parts are the validator's job)."""
    return [p for p in _instances(spec) if p.part_id in lib]


# --- firmware -------------------------------------------------------------------------------------


def parse_pins_h(text: str) -> dict[str, str]:
    return {
        m[1]: m[2]
        for m in re.finditer(r"^\s*#define\s+(PIN_\w+)\s+(\w+)\b", text, re.MULTILINE)
    }


def check_pins(pins_h: str, spec: ProjectSpec) -> list[str]:
    """pins.h defines exactly PIN_<REF>_<PIN> <pin> for every connection to a signal pin."""
    expected = {
        f"PIN_{c.part_ref}_{c.part_pin}".upper(): code
        for c in spec.connections
        if (code := pin_code(c.mcu_pin))
    }
    actual = parse_pins_h(pins_h)
    problems = [
        f"pins.h: {name} is {actual.get(name)}, spec says {n}"
        for name, n in sorted(expected.items())
        if actual.get(name) != n
    ]
    problems += [
        f"pins.h: {name} isn't in spec.connections"
        for name in sorted(set(actual) - set(expected))
    ]
    return problems


# --- layout ---------------------------------------------------------------------------------------


def _footprint(p, lib: PartLibrary, ref_to_part: dict[str, str]):
    dims = lib.get(ref_to_part[p.ref]).board_mm
    l, w = (dims.w, dims.l) if p.rot_deg in (90, 270) else (dims.l, dims.w)
    return p.x_mm, p.y_mm, p.x_mm + l, p.y_mm + w, p.z_mm + dims.h


def check_layout(layout: Layout, spec: ProjectSpec, lib: PartLibrary) -> list[str]:
    """One placement per inside part (mcu included), sorted by ref; each inside the cavity, none
    overlapping, and against_wall really touching that wall."""
    inside = sorted(p.ref for p in _known(spec, lib) if mounting(p, lib) == "inside")
    refs = [p.ref for p in layout.placements]
    problems = []
    if refs != inside:
        problems.append(
            f"layout: placements {refs}, expected sorted inside refs {inside}"
        )
    ref_to_part = {p.ref: p.part_id for p in _known(spec, lib)}
    L, W, H = layout.cavity_mm
    boxes = {}
    for p in layout.placements:
        if p.ref not in ref_to_part:
            continue
        x0, y0, x1, y1, top = boxes[p.ref] = _footprint(p, lib, ref_to_part)
        if x0 < -TOL or y0 < -TOL or x1 > L + TOL or y1 > W + TOL or p.z_mm < -TOL:
            problems.append(
                f"layout: {p.ref} spans x {x0:.2f}..{x1:.2f}, y {y0:.2f}..{y1:.2f}, outside the {L} x {W} cavity"
            )
        if top > H + TOL:
            problems.append(
                f"layout: {p.ref} top at z={top:.2f} is above the cavity height {H}"
            )
        wall_gap = {"left": x0, "right": L - x1, "front": y0, "back": W - y1}
        if p.against_wall and abs(wall_gap[p.against_wall]) > TOL:
            problems.append(
                f"layout: {p.ref} is against_wall={p.against_wall} but is {wall_gap[p.against_wall]:.2f} mm away"
            )
    for (a, ba), (b, bb) in combinations(sorted(boxes.items()), 2):
        if (
            min(ba[2], bb[2]) - max(ba[0], bb[0]) > TOL
            and min(ba[3], bb[3]) - max(ba[1], bb[1]) > TOL
        ):
            problems.append(f"layout: {a} and {b} overlap")
    return problems


# --- enclosure ------------------------------------------------------------------------------------


def check_cutouts(
    manifest: EnclosureManifest, spec: ProjectSpec, lib: PartLibrary
) -> list[str]:
    """Every feature of every inside part has a cutout (top features in the lid); every external part
    has a cable hole; no cutout serves a part that isn't in the spec; centres lie on their face."""
    expected = []
    for p in _known(spec, lib):
        part = lib.get(p.part_id)
        if mounting(p, lib) == "external":
            expected.append((p.ref, "cable"))
        else:
            expected += [(p.ref, f.kind) for f in part.features]
    actual = [(c.for_ref, c.feature) for c in manifest.cutouts]
    problems = [
        f"enclosure manifest: no {kind} cutout for {ref}"
        for ref, kind in sorted(set(expected) - set(actual))
    ]
    problems += [
        f"enclosure manifest: {kind} cutout for {ref}, which has no such feature in the spec"
        for ref, kind in sorted(set(actual) - set(expected))
    ]
    top_features = {
        (p.ref, f.kind)
        for p in _known(spec, lib)
        for f in lib.get(p.part_id).features
        if f.face == "top"
    }
    L, W, H = manifest.cavity_mm
    bounds = {
        "top": (L, W),
        "front": (L, H),
        "back": (L, H),
        "left": (W, H),
        "right": (W, H),
    }
    for c in manifest.cutouts:
        if (c.for_ref, c.feature) in top_features and c.face != "top":
            problems.append(
                f"enclosure manifest: {c.for_ref} {c.feature} faces up but is cut in {c.face}"
            )
        (u, v), (bu, bv) = c.center_mm, bounds[c.face]
        if not (-TOL <= u <= bu + TOL and -TOL <= v <= bv + TOL):
            problems.append(
                f"enclosure manifest: {c.for_ref} {c.feature} centre {c.center_mm} is off the {c.face} face ({bu} x {bv})"
            )
    unmeasured = sorted(
        p.ref for p in _known(spec, lib) if lib.get(p.part_id).dims_source != "measured"
    )
    if sorted(manifest.unmeasured_refs) != unmeasured:
        problems.append(
            f"enclosure manifest: unmeasured_refs {sorted(manifest.unmeasured_refs)}, expected {unmeasured}"
        )
    if manifest.wall_mm != spec.enclosure.wall_mm:
        problems.append(
            f"enclosure manifest: wall_mm {manifest.wall_mm}, spec says {spec.enclosure.wall_mm}"
        )
    return problems


# --- BOM and wiring -------------------------------------------------------------------------------


def check_bom(bom: Bom, spec: ProjectSpec, lib: PartLibrary) -> list[str]:
    """One line per part id in the spec with the right refs, quantities, owned parts and totals."""
    problems = []
    by_part: dict[str, list[PartInstance]] = {}
    for p in _instances(spec):
        by_part.setdefault(p.part_id, []).append(p)
    lines = {line.part_id: line for line in bom.lines}
    for pid in sorted(set(by_part) - set(lines)):
        problems.append(f"bom: no line for {pid}")
    for pid in sorted(set(lines) - set(by_part)):
        problems.append(f"bom: line for {pid}, which isn't in the spec")
    for pid, line in sorted(lines.items()):
        if pid not in by_part:
            continue
        refs = sorted(p.ref for p in by_part[pid])
        qty = sum(p.qty for p in by_part[pid])
        owned = min(spec.user.owned.get(pid, 0), qty)
        total = (qty - owned) * (line.unit_price_usd or 0.0)
        if sorted(line.refs) != refs:
            problems.append(f"bom: {pid} refs {line.refs}, expected {refs}")
        if line.qty != qty:
            problems.append(f"bom: {pid} qty {line.qty}, expected {qty}")
        if line.owned_qty != owned:
            problems.append(f"bom: {pid} owned_qty {line.owned_qty}, expected {owned}")
        if abs(line.line_total_usd - total) > TOL:
            problems.append(
                f"bom: {pid} line_total_usd {line.line_total_usd}, expected {total:.2f}"
            )
        if pid in lib and line.name != lib.get(pid).name:
            problems.append(
                f"bom: {pid} name {line.name!r}, library says {lib.get(pid).name!r}"
            )
    line_sum = sum(line.line_total_usd for line in bom.lines)
    if abs(bom.total_usd - line_sum) > TOL:
        problems.append(f"bom: total_usd {bom.total_usd}, lines sum to {line_sum:.2f}")
    budget = spec.user.budget_usd
    if bom.budget_usd != budget:
        problems.append(f"bom: budget_usd {bom.budget_usd}, spec says {budget}")
    over = budget is not None and bom.total_usd > budget + 1e-9  # one cent over is over
    if bom.over_budget != over:
        problems.append(
            f"bom: over_budget {bom.over_budget} with total {bom.total_usd} and budget {budget}"
        )
    if bom.spec_rev != spec.rev:
        problems.append(f"bom: spec_rev {bom.spec_rev}, spec is rev {spec.rev}")
    return problems


def check_wiring(wiring: Wiring, spec: ProjectSpec, lib: PartLibrary) -> list[str]:
    """One row per connection, with the library's pin type and part name."""
    problems = []
    ref_to_part = {p.ref: p.part_id for p in _instances(spec)}
    key = lambda r: (r.part_ref, r.part_pin, r.mcu_pin, r.bus)
    rows = sorted(key(r) for r in wiring.rows)
    conns = sorted(key(c) for c in spec.connections)
    if rows != conns:
        missing = sorted(set(conns) - set(rows))
        extra = sorted(set(rows) - set(conns))
        problems.append(
            f"wiring: rows don't match connections; missing {missing}, extra {extra}"
        )
    for r in wiring.rows:
        pid = ref_to_part.get(r.part_ref)
        if pid is None or pid not in lib:
            continue
        if r.pin_type != lib.pin_type(pid, r.part_pin):
            problems.append(
                f"wiring: {r.part_ref}.{r.part_pin} pin_type {r.pin_type}, library says {lib.pin_type(pid, r.part_pin)}"
            )
        if r.part_name != lib.get(pid).name:
            problems.append(
                f"wiring: {r.part_ref} part_name {r.part_name!r}, library says {lib.get(pid).name!r}"
            )
    if wiring.spec_rev != spec.rev:
        problems.append(f"wiring: spec_rev {wiring.spec_rev}, spec is rev {spec.rev}")
    return problems


# --- run directory --------------------------------------------------------------------------------


def check_run_dir(
    run_dir: Path, lib: PartLibrary | None = None, *, engine: bool = True
) -> list[str]:
    """Every artifact the manifest lists exists and was built from the current spec rev, and every
    generated file present agrees with the spec. engine=False skips manifest.json, which only the
    run engine writes (for runs made by calling the StageRunner directly)."""
    lib = lib or load_library()
    run_dir = Path(run_dir)
    spec = ProjectSpec.model_validate_json((run_dir / "spec.json").read_text())
    problems = []
    manifest = RunManifest(spec_rev=spec.rev, artifacts={})
    if engine:
        manifest = RunManifest.model_validate_json(
            (run_dir / "manifest.json").read_text()
        )
    if manifest.spec_rev != spec.rev:
        problems.append(
            f"manifest.json: spec_rev {manifest.spec_rev}, spec.json is rev {spec.rev}"
        )
    for name, info in sorted(manifest.artifacts.items()):
        if not (run_dir / info.path).is_file():
            problems.append(f"manifest.json: {name} -> {info.path} doesn't exist")
        if info.spec_rev != spec.rev:
            problems.append(
                f"manifest.json: {name} is from rev {info.spec_rev}, spec is rev {spec.rev} (stale)"
            )

    def present(rel: str) -> Path | None:
        path = run_dir / rel
        return path if path.is_file() else None

    if path := present("firmware/include/pins.h"):
        problems += check_pins(path.read_text(), spec)
    if path := present("cad/layout.json"):
        problems += check_layout(
            Layout.model_validate_json(path.read_text()), spec, lib
        )
    if path := present("cad/manifest.json"):
        enclosure = EnclosureManifest.model_validate_json(path.read_text())
        problems += check_cutouts(enclosure, spec, lib)
        if enclosure.spec_rev != spec.rev:
            problems.append(
                f"cad/manifest.json: spec_rev {enclosure.spec_rev}, spec is rev {spec.rev}"
            )
    if path := present("bom.json"):
        problems += check_bom(Bom.model_validate_json(path.read_text()), spec, lib)
    if path := present("wiring.json"):
        problems += check_wiring(
            Wiring.model_validate_json(path.read_text()), spec, lib
        )
    return problems


# --- event stream ---------------------------------------------------------------------------------


def load_events(path: Path) -> list[Event]:
    return [
        Event.model_validate_json(line)
        for line in Path(path).read_text().splitlines()
        if line.strip()
    ]


def check_events(events: list[Event]) -> list[str]:
    """One run, seq contiguous from the first event, spec_rev never going back, ending in done/passed."""
    if not events:
        return ["events: none"]
    problems = []
    if len({e.run_id for e in events}) != 1:
        problems.append(f"events: several run ids {sorted({e.run_id for e in events})}")
    seqs = [e.seq for e in events]
    if seqs != list(range(seqs[0], seqs[0] + len(seqs))):
        problems.append(f"events: seq not contiguous: {seqs}")
    revs = [e.spec_rev for e in events]
    if revs != sorted(revs):
        problems.append(f"events: spec_rev goes backwards: {revs}")
    last = events[-1]
    if (last.stage, last.status) != ("done", "passed"):
        problems.append(
            f"events: last event is {last.stage}/{last.status}, not done/passed: {last.message}"
        )
    return problems


def final_statuses(events: list[Event]) -> dict[str, str]:
    """Last status of each stage."""
    return {e.stage: e.status for e in events}


def failed_stages(
    events: list[Event], may_skip: tuple[str, ...] = ("simulate",)
) -> list[str]:
    """Pipeline stages (and checks) that didn't end passed (or skipped, for `may_skip`: the mode in
    HARDWARE.md decides whether simulate runs), each with its last status and message."""
    last = {e.stage: e for e in events}
    ok = lambda s: (
        s in last
        and (
            last[s].status == "passed"
            or (last[s].status == "skipped" and s in may_skip)
        )
    )
    return [
        f"{s}: {last[s].status} {last[s].message}" if s in last else f"{s}: never ran"
        for s in (*PIPELINE, "checks")
        if not ok(s)
    ]


def stages_run(events: list[Event], after_seq: int = 0) -> set[str]:
    """Stages (not plan/done) that started running after the given seq."""
    return {
        e.stage
        for e in events
        if e.seq > after_seq
        and e.status == "running"
        and e.stage not in ("plan", "done")
    }
