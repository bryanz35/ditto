"""Cross-domain checks over a run directory (T21): do the generated files still agree with the spec?

Runs after every (re)run, in the `checks` stage. A file that isn't in the run directory is skipped:
its own stage already reported why. Every problem is an error; `ok` is true only when none are found.

Error codes (one per check, so each maps to one row kind in the checks panel):
- pins_mismatch: firmware/include/pins.h disagrees with spec.connections.
- layout_mismatch: cad/layout.json has a placement missing, outside the cavity, overlapping or off its wall.
- cutout_mismatch: cad/manifest.json lacks a cutout for a part feature, or has one nothing needs.
- bom_mismatch: bom.json has a line that doesn't map to the spec's parts, or wrong quantities or totals.
- wiring_mismatch: wiring.json rows don't match spec.connections or the library.
- stale_artifact: an artifact was built from an older spec rev than the spec's.
- missing_artifact: manifest.json lists a file that isn't in the run directory.
"""

from collections.abc import Callable
from pathlib import Path

from backend.contracts.artifacts import Bom, EnclosureManifest, RunManifest, Wiring
from backend.contracts.parts import PartLibrary
from backend.contracts.results import ToolError, ToolResult
from backend.contracts.spec import Layout, ProjectSpec

# shortcut: Q's invariant helpers live under tests/ (contract request T21-invariants-location);
# switch this import when the Integrator moves them under backend/.
from tests.integration import invariants as inv

HINTS = {
    "pins_mismatch": "rerun the firmware stage so pins.h is regenerated from spec.connections",
    "layout_mismatch": "rerun the layout stage; if it persists, the cavity or parts in the spec don't fit",
    "cutout_mismatch": "rerun the enclosure stage so cutouts are recomputed from the spec's part features",
    "bom_mismatch": "rerun the bom stage so lines are rebuilt from the spec's parts",
    "wiring_mismatch": "rerun the wiring stage so rows are rebuilt from spec.connections",
    "stale_artifact": "rerun the stage that produced this artifact at the current spec rev",
    "missing_artifact": "rerun the stage that produced this artifact",
}

# (code, file relative to the run dir, check(text) -> problems)
Check = Callable[[str, ProjectSpec, PartLibrary], list[str]]
CHECKS: list[tuple[str, str, Check]] = [
    (
        "pins_mismatch",
        "firmware/include/pins.h",
        lambda t, s, _lib: inv.check_pins(t, s),
    ),
    (
        "layout_mismatch",
        "cad/layout.json",
        lambda t, s, lib: inv.check_layout(Layout.model_validate_json(t), s, lib),
    ),
    (
        "cutout_mismatch",
        "cad/manifest.json",
        lambda t, s, lib: _enclosure(EnclosureManifest.model_validate_json(t), s, lib),
    ),
    (
        "bom_mismatch",
        "bom.json",
        lambda t, s, lib: inv.check_bom(Bom.model_validate_json(t), s, lib),
    ),
    (
        "wiring_mismatch",
        "wiring.json",
        lambda t, s, lib: inv.check_wiring(Wiring.model_validate_json(t), s, lib),
    ),
]


def _enclosure(
    manifest: EnclosureManifest, spec: ProjectSpec, lib: PartLibrary
) -> list[str]:
    problems = inv.check_cutouts(manifest, spec, lib)
    if manifest.spec_rev != spec.rev:
        problems.append(
            f"cad/manifest.json: spec_rev {manifest.spec_rev}, spec is rev {spec.rev}"
        )
    return problems


# spec field each error is about (ToolError.field is a spec path)
FIELDS = {
    "pins_mismatch": "connections",
    "wiring_mismatch": "connections",
    "layout_mismatch": "parts",
    "cutout_mismatch": "parts",
    "bom_mismatch": "parts",
    "stale_artifact": "rev",
    "missing_artifact": None,
}


def _error(code: str, message: str) -> ToolError:
    return ToolError(code=code, message=message, field=FIELDS[code], hint=HINTS[code])


def cross_checks(run_dir: Path, spec: ProjectSpec, lib: PartLibrary) -> ToolResult:
    run_dir = Path(run_dir)
    errors: list[ToolError] = []
    flagged: set[str] = (
        set()
    )  # stale or missing: their content can't be expected to match

    manifest_path = run_dir / "manifest.json"
    if manifest_path.is_file():
        manifest = RunManifest.model_validate_json(manifest_path.read_text())
        for name, info in sorted(manifest.artifacts.items()):
            if not (run_dir / info.path).is_file():
                message = (
                    f"manifest.json lists {name} at {info.path}, which doesn't exist"
                )
                errors.append(_error("missing_artifact", message))
            elif info.spec_rev != spec.rev:
                message = (
                    f"{info.path} ({name}, {info.stage} stage) was built from spec rev "
                    f"{info.spec_rev}; the spec is rev {spec.rev}"
                )
                errors.append(_error("stale_artifact", message))
            else:
                continue
            flagged.add(info.path)

    for code, rel, check in CHECKS:
        path = run_dir / rel
        if rel in flagged or not path.is_file():
            continue
        try:
            problems = check(path.read_text(), spec, lib)
        except ValueError as exc:  # pydantic ValidationError, bad JSON
            problems = [f"{rel} doesn't parse: {exc}"]
        for problem in problems:
            stale = "spec_rev" in problem  # the helpers' wording for a rev mismatch
            errors.append(_error("stale_artifact" if stale else code, problem))

    return ToolResult(
        ok=not errors, errors=errors, log=f"{len(errors)} cross-domain problem(s)"
    )
