"""Which stages read which spec fields, and what must rerun after a spec change
(docs/PROJECT_PLAN.md, "Keeping the sub-tasks aligned")."""

DEPENDS_ON: dict[str, set[str]] = {  # stage -> spec fields or stages it reads
    # an edit reruns only what this map names and carries every other stage forward, so a field a
    # stage's tools start reading must be added here (tests/unit/api/test_deps.py pins it down)
    "validate": {
        "mcu",
        "parts",
        "connections",
        "firmware",
        "custom_parts",
    },  # needs_wifi vs ADC2
    "layout": {"mcu", "parts", "enclosure", "custom_parts"},
    "enclosure": {"layout", "enclosure", "user"},  # user.printer
    "assembly": {"layout", "enclosure"},
    "firmware": {"mcu", "parts", "connections", "firmware", "custom_parts"},
    "wiring": {"mcu", "parts", "connections", "custom_parts"},
    "simulate": {"firmware", "wiring"},
    "bom": {"mcu", "parts", "user", "custom_parts"},
}
ORDER = list(DEPENDS_ON)  # topological


def _without_looks(spec: dict) -> dict:
    # a custom part's look is the 3D view's alone (and specs saved before it existed lack the key)
    parts = spec.get("custom_parts") or []
    return {
        **spec,
        "custom_parts": [{k: v for k, v in p.items() if k != "look"} for p in parts],
    }


def changed_fields(old: dict, new: dict) -> set[str]:
    old, new = _without_looks(old), _without_looks(new)
    return {k for k in new if old.get(k) != new.get(k)}


def stages_to_rerun(changed: set[str]) -> list[str]:
    dirty = set(changed)
    for stage in ORDER:
        if DEPENDS_ON[stage] & dirty:
            dirty.add(stage)  # later stages that read this stage rerun too
    return [s for s in ORDER if s in dirty]
