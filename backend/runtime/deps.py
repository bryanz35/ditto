"""Which stages read which spec fields, and what must rerun after a spec change
(docs/PROJECT_PLAN.md, "Keeping the sub-tasks aligned")."""

DEPENDS_ON: dict[str, set[str]] = {  # stage -> spec fields or stages it reads
    # an edit reruns only what this map names and carries every other stage forward, so a field a
    # stage's tools start reading must be added here (tests/unit/api/test_deps.py pins it down)
    "validate": {"mcu", "parts", "connections", "firmware"},  # needs_wifi vs ADC2
    "layout": {"mcu", "parts", "enclosure"},
    "enclosure": {"layout", "enclosure", "user"},  # user.printer
    "assembly": {"layout", "enclosure"},
    "firmware": {"mcu", "parts", "connections", "firmware"},
    "wiring": {"mcu", "parts", "connections"},
    "simulate": {"firmware", "wiring"},
    "bom": {"mcu", "parts", "user"},
}
ORDER = list(DEPENDS_ON)  # topological


def changed_fields(old: dict, new: dict) -> set[str]:
    return {k for k in new if old.get(k) != new.get(k)}


def stages_to_rerun(changed: set[str]) -> list[str]:
    dirty = set(changed)
    for stage in ORDER:
        if DEPENDS_ON[stage] & dirty:
            dirty.add(stage)  # later stages that read this stage rerun too
    return [s for s in ORDER if s in dirty]
