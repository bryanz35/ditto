"""Reference implementation of the scene pipeline, ported from the browser spike (instruction_spike.html).

Self-contained on purpose: it does NOT import the real spec/library code. Port the functions into
backend/tools/{layout,wiring,instructions}.py and replace the inline LIBRARY / PLACEMENTS / CONNECTIONS
with the real ProjectSpec, parts library and layout.py output.

Run:  python scene_reference.py <out_dir>
Writes layout.json, wiring.json, instructions.json, library.json and validates them against scene_contracts.py.
"""

import json
import math
import sys
from pathlib import Path

import numpy as np
from scene_contracts import (
    Action,
    Cutout,
    Dims,
    Enclosure,
    Header,
    Instructions,
    Layout,
    LidOpening,
    LookShape,
    Need,
    PinWorld,
    PrintItem,
    PrintLayout,
    SceneObject,
    Step,
    ViewerPart,
    Wire,
    Wiring,
)

# ------------------------------------------------------------------ frames
TO_WEB = np.array(
    [[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1]], dtype=float
)  # CAD (x, y, z) Z-up  ->  web (x, z, -y) Y-up


def T(x, y, z):
    m = np.eye(4)
    m[:3, 3] = (x, y, z)
    return m


def Rz(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    m = np.eye(4)
    m[0, 0], m[0, 1], m[1, 0], m[1, 1] = c, -s, s, c
    return m


def xf(m, p):
    return tuple(round(float(v), 3) for v in (m @ np.array([*p, 1.0]))[:3])


def col_major(m):
    return [
        round(float(v), 4) for v in m.flatten(order="F")
    ]  # three.js Matrix4.fromArray order


# ------------------------------------------------------------------ inputs (stand-ins for library YAML / spec / layout.py)
# Part-local coordinates: u along length from the corner, v along width, h up from the PCB bottom.
LIBRARY: dict[str, ViewerPart] = {
    p.id: p
    for p in [
        ViewerPart(
            id="esp32_devkitc",
            name="ESP32 DevKitC",
            short_name="ESP32 board",
            category="microcontroller",
            board_mm={"l": 55, "w": 28, "h": 1.6},
            pcb_color="#2a2d35",
            mount_holes=[
                (1.6, 22.5),
                (1.6, 5.5),
                (53.4, 22.5),
                (53.4, 5.5),
            ],  # the real DevKitC has none: placeholder
            features=[{"kind": "usb", "face": "left", "at": [1.5, 14], "size": [8, 3]}],
            headers=[
                Header(
                    id="J2",
                    origin=(50.36, 1.3),
                    pitch=(-2.54, 0),
                    pins=[
                        "3V3",
                        "EN",
                        "GPIO36",
                        "GPIO39",
                        "GPIO34",
                        "GPIO35",
                        "GPIO32",
                        "GPIO33",
                        "GPIO25",
                        "GPIO26",
                        "GPIO27",
                        "GPIO14",
                        "GPIO12",
                        "GND",
                        "GPIO13",
                        "SD2",
                        "SD3",
                        "CMD",
                        "5V",
                    ],
                ),
                Header(
                    id="J3",
                    origin=(50.36, 26.7),
                    pitch=(-2.54, 0),
                    pins=[
                        "GND",
                        "GPIO23",
                        "GPIO22",
                        "TX",
                        "RX",
                        "GPIO21",
                        "GND",
                        "GPIO19",
                        "GPIO18",
                        "GPIO5",
                        "GPIO17",
                        "GPIO16",
                        "GPIO4",
                        "GPIO0",
                        "GPIO2",
                        "GPIO15",
                        "SD1",
                        "SD0",
                        "CLK",
                    ],
                ),
            ],
            look=[
                LookShape(
                    shape="box", at=(40, 14), size=(23, 17, 0.8), color="#33363f"
                ),
                LookShape(
                    shape="box",
                    at=(38, 14),
                    size=(17.6, 15.8, 3.1),
                    color="#c9ccd2",
                    metal=0.6,
                ),
                LookShape(
                    shape="box",
                    at=(1.5, 14),
                    size=(6, 8, 3),
                    color="#c9ccd2",
                    metal=0.6,
                ),
                LookShape(
                    shape="box", at=(6, 5.4), size=(3.5, 3, 1.6), color="#f2f2f2"
                ),
                LookShape(
                    shape="box", at=(6, 22.6), size=(3.5, 3, 1.6), color="#f2f2f2"
                ),
                LookShape(
                    shape="box", at=(12.5, 17), size=(5, 6, 1.4), color="#151515"
                ),
                LookShape(
                    shape="led", at=(9, 9), size=(1.6, 1.0, 0.8), color="#ff4d4d"
                ),
            ],
            price_usd=6.5,
        ),
        ViewerPart(
            id="ssd1306_096_i2c",
            name='0.96" OLED screen',
            short_name="screen",
            category="display",
            board_mm={"l": 27.3, "w": 27.8, "h": 1.2},
            pcb_color="#1f4e9c",
            mount_holes=[(2.25, 25.8), (25.05, 25.8), (2.25, 2.0), (25.05, 2.0)],
            features=[
                {
                    "kind": "display_window",
                    "face": "top",
                    "at": [13.65, 13.4],
                    "size": [24, 13],
                }
            ],
            headers=[
                Header(
                    id="H1",
                    origin=(9.84, 26.1),
                    pitch=(2.54, 0),
                    side="bottom",
                    pins=["GND", "VCC", "SCL", "SDA"],
                )
            ],
            look=[
                LookShape(
                    shape="box", at=(13.65, 13.4), size=(26, 16, 1.4), color="#0d1117"
                ),
                LookShape(shape="screen", at=(13.65, 13.4), size=(22, 11, 0)),
                LookShape(
                    shape="box", at=(13.65, 4.3), size=(9, 2.6, 0.3), color="#c8a35a"
                ),
            ],
            price_usd=4.0,
        ),
        ViewerPart(
            id="passive_buzzer",
            name="Passive buzzer module",
            short_name="beeper",
            category="output",
            board_mm={"l": 18.5, "w": 15, "h": 1.6},
            pcb_color="#2f6b3f",
            mount_holes=[(15.75, 2.0), (15.75, 13.0)],
            features=[
                {"kind": "sound_port", "face": "top", "at": [9.75, 7.5], "r": 1.1}
            ],
            headers=[
                Header(
                    id="H1", origin=(1.5, 8.77), pitch=(0, -2.54), pins=["SIG", "GND"]
                )
            ],
            look=[
                LookShape(shape="cyl", at=(9.75, 7.5), r=5.5, h=8, color="#1c1c1c"),
                LookShape(shape="cyl", at=(9.75, 7.5), r=1.0, h=8.1, color="#5a5a5a"),
            ],
            price_usd=1.0,
        ),
    ]
}

SPEC_REV = 7
SKILL_DEFAULT = "beginner"
REASONS = {
    "mcu": "The brain. It runs your timer code, and has Wi-Fi if you want it later.",
    "oled1": "Shows the countdown big enough to read from across the desk.",
    "buzz1": "Beeps when a focus session ends.",
}
# what layout.py already computes (CAD frame): board centre, rotation, standoff height
PLACEMENTS = [
    {
        "ref": "mcu",
        "part_id": "esp32_devkitc",
        "center_xy": (-18, 0),
        "rot_deg": 0,
        "standoff_mm": 5,
    },
    {
        "ref": "oled1",
        "part_id": "ssd1306_096_i2c",
        "center_xy": (30, 10),
        "rot_deg": 0,
        "standoff_mm": 30,
    },
    {
        "ref": "buzz1",
        "part_id": "passive_buzzer",
        "center_xy": (30, -19),
        "rot_deg": 0,
        "standoff_mm": 5,
    },
]
CONNECTIONS = [  # spec.json connections, unchanged shape
    {"part_ref": "oled1", "part_pin": "GND", "mcu_pin": "GND", "bus": "power"},
    {"part_ref": "oled1", "part_pin": "VCC", "mcu_pin": "3V3", "bus": "power"},
    {"part_ref": "oled1", "part_pin": "SCL", "mcu_pin": "GPIO22", "bus": "i2c"},
    {"part_ref": "oled1", "part_pin": "SDA", "mcu_pin": "GPIO21", "bus": "i2c"},
    {"part_ref": "buzz1", "part_pin": "SIG", "mcu_pin": "GPIO25", "bus": "gpio"},
    {"part_ref": "buzz1", "part_pin": "GND", "mcu_pin": "GND", "bus": "power"},
]
ENCLOSURE_CAD = {
    "inner": (100, 62, 36),
    "wall": 2.4,
    "floor": 2.0,
    "lid": 2.0,
}  # inner (l, w, h) in CAD x, y, z
LID_SCREWS_XY = [(-47, 28), (47, 28), (-47, -28), (47, -28)]
PRINTER_BED = (256, 256)

# ------------------------------------------------------------------ layout
FLOOR, INNER_H, LID_T = (
    ENCLOSURE_CAD["floor"],
    ENCLOSURE_CAD["inner"][2],
    ENCLOSURE_CAD["lid"],
)
LID_Y = FLOOR + INNER_H
PL = {p["ref"]: p for p in PLACEMENTS}


def part(ref):
    return LIBRARY[PL[ref]["part_id"]]


def local_to_cad(ref):
    p, b = PL[ref], part(ref).board_mm
    cx, cy = p["center_xy"]
    return (
        T(cx, cy, FLOOR + p["standoff_mm"])
        @ Rz(p["rot_deg"])
        @ T(-b.l / 2, -b.w / 2, 0)
    )


def local_to_world(ref):
    return TO_WEB @ local_to_cad(ref)


def top_height(ref):
    """Height of the tallest thing on the board above its bottom face (for clearance + explode)."""
    pt, h = part(ref), part(ref).board_mm.h
    tall = [h + (s.h or (s.size[2] if s.size else 0)) for s in pt.look]
    tall += [h + hd.pin_len_mm for hd in pt.headers if hd.side == "top"]
    return max([h, *tall])


def build_layout() -> Layout:
    l, w, h = ENCLOSURE_CAD["inner"]
    wall = ENCLOSURE_CAD["wall"]
    cutouts, lid_openings = [], []
    for ref in PL:
        m = local_to_world(ref)
        for f in part(ref).features:
            if f["kind"] == "usb":
                u, v = f["at"]
                x, y, z = xf(m, (u, v, part(ref).board_mm.h + f["size"][1] / 2))
                along = z if f["face"] in ("left", "right") else x
                cutouts.append(
                    Cutout(
                        face=f["face"],
                        for_ref=f"{ref}.usb",
                        center=(along, y),
                        size=(12, 9),
                    )
                )
            if f["kind"] == "display_window" and f["face"] == "top":
                x, _, z = xf(m, (*f["at"], 0))
                lid_openings.append(
                    LidOpening(
                        for_ref=ref,
                        shape="rect",
                        center_xz=(x, z),
                        size_xz=tuple(f["size"]),
                    )
                )
            if f["kind"] == "sound_port":
                x, _, z = xf(m, (*f["at"], 0))
                for dx, dz in [(0, 0), (3.2, 0), (-3.2, 0), (0, 3.2), (0, -3.2)]:
                    lid_openings.append(
                        LidOpening(
                            for_ref=ref,
                            shape="circle",
                            center_xz=(x + dx, z + dz),
                            r=f["r"],
                        )
                    )
    enclosure = Enclosure(
        inner=Dims(l=l, w=w, h=h),
        wall=wall,
        floor=FLOOR,
        lid_thickness=LID_T,
        cutouts=cutouts,
        lid_openings=lid_openings,
        lid_screw_holes=[(x, -y) for x, y in LID_SCREWS_XY],
        standoffs=[
            (*xf(local_to_world(r), (u, v, 0))[::2], FLOOR + PL[r]["standoff_mm"])
            for r in PL
            for u, v in part(r).mount_holes
        ],
    )

    objs: list[SceneObject] = [
        SceneObject(
            ref="base",
            kind="printed",
            name="Case base (3D-printed)",
            position=(0, 0, 0),
            reason="Designed around these exact boards: a post under every screw hole, a hole for the USB plug.",
        ),
    ]
    order = mount_order()
    max_top_inside = 0.0
    for i, ref in enumerate(order):
        m, pt = local_to_world(ref), part(ref)
        under_lid_opening = any(
            o.for_ref == ref and o.shape == "rect" for o in lid_openings
        )
        if under_lid_opening:  # slide sideways out of the case footprint so the exploded lid doesn't hide it
            min_x = min(
                xf(m, (u, v, 0))[0]
                for u in (0, pt.board_mm.l)
                for v in (0, pt.board_mm.w)
            )
            explode = (round(l / 2 + wall - min_x + 8, 1), 22.0, 0.0)
        else:
            explode = (0.0, 28.0 + 6 * i, 0.0)
            max_top_inside = max(
                max_top_inside,
                FLOOR + PL[ref]["standoff_mm"] + top_height(ref) + explode[1],
            )
        objs.append(
            SceneObject(
                ref=ref,
                kind="board",
                part_id=pt.id,
                name=pt.name,
                reason=REASONS.get(ref, ""),
                parent="base",
                position=xf(m, (0, 0, 0)),
                local_to_world=col_major(m),
                explode=explode,
            )
        )
        for k, (u, v) in enumerate(pt.mount_holes):
            objs.append(
                SceneObject(
                    ref=f"{ref}.s{k + 1}",
                    kind="screw",
                    name="M2.5 × 6 mm screw",
                    parent=ref,
                    reason=f"Holds the {pt.short_name} on its post.",
                    position=xf(m, (u, v, pt.board_mm.h)),
                    explode=(explode[0], explode[1] + 18, explode[2]),
                )
            )
    lid_explode = round(max(max_top_inside, LID_Y) - LID_Y + 35, 1)
    objs.append(
        SceneObject(
            ref="lid",
            kind="printed",
            name="Lid (3D-printed)",
            position=(0, LID_Y, 0),
            reason="A window over the screen and small holes so you can hear the beeper.",
            explode=(0, lid_explode, 0),
        )
    )
    for k, (x, z) in enumerate(enclosure.lid_screw_holes):
        objs.append(
            SceneObject(
                ref=f"lid.s{k + 1}",
                kind="screw",
                name="M2.5 × 6 mm screw",
                parent="lid",
                reason="Holds the lid on.",
                position=(x, LID_Y + LID_T, z),
                explode=(0, lid_explode + 22, 0),
            )
        )
    usb = next(c for c in cutouts if c.for_ref == "mcu.usb")
    m = local_to_world("mcu")
    f = next(f for f in part("mcu").features if f["kind"] == "usb")
    tip = xf(
        m, (f["at"][0] - 3, f["at"][1], part("mcu").board_mm.h + f["size"][1] / 2)
    )  # receptacle mouth
    axis = {
        "left": (-1, 0, 0),
        "right": (1, 0, 0),
        "front": (0, 0, 1),
        "back": (0, 0, -1),
    }[usb.face]
    objs.append(
        SceneObject(
            ref="usb",
            kind="cable",
            name="USB cable",
            position=tip,
            axis=axis,
            reason="Powers the timer and uploads the code. Already in your inventory.",
            explode=tuple(34 * a for a in axis),
        )
    )
    W = w + 2 * wall
    printing = PrintLayout(
        bed_mm=PRINTER_BED,
        items=[
            PrintItem(ref="base", position=(0, 0, 0)),
            PrintItem(ref="lid", position=(0, 0, round(W + 12, 1))),
        ],
    )
    return Layout(
        rev=SPEC_REV, enclosure=enclosure, objects=objs, print_layout=printing
    )


def mount_order():
    """MCU first, then shortest parts first so tall ones never block the screwdriver."""
    rest = sorted(
        (r for r in PL if r != "mcu"),
        key=lambda r: (PL[r]["standoff_mm"] + top_height(r), r),
    )
    return ["mcu", *rest]


# ------------------------------------------------------------------ wiring
WIRE_COLORS = [
    ("#2e9e4f", "green"),
    ("#f57c00", "orange"),
    ("#8e24aa", "purple"),
    ("#eceff1", "white"),
]


def header_pins(ref) -> list[PinWorld]:
    m, pt, out = local_to_world(ref), part(ref), []
    for hd in pt.headers:
        hz = pt.board_mm.h + hd.pin_len_mm if hd.side == "top" else -hd.pin_len_mm
        for i, name in enumerate(hd.pins):
            u, v = hd.origin[0] + hd.pitch[0] * i, hd.origin[1] + hd.pitch[1] * i
            out.append(
                PinWorld(
                    id=f"{ref}:{hd.id}:{i}",
                    part_ref=ref,
                    name=name,
                    position=xf(m, (u, v, hz)),
                    dir=1 if hd.side == "top" else -1,
                )
            )
    return out


class PinConflict(Exception):
    """Raise -> orchestrator gets request_change(field="connections", reason=..., options=[...])."""


def wire_color(c, k):
    p = c["part_pin"].upper()
    if "GND" in p:
        return ("#26282c", "black")
    if c["mcu_pin"] in ("3V3", "5V"):
        return ("#e53935", "red")
    if p == "SCL":
        return ("#f6c20d", "yellow")
    if p == "SDA":
        return ("#1e88e5", "blue")
    return WIRE_COLORS[k % len(WIRE_COLORS)]


def build_wiring() -> Wiring:
    used, pins, wires, k = set(), {}, [], 0
    for c in CONNECTIONS:
        end = next(p for p in header_pins(c["part_ref"]) if p.name == c["part_pin"])
        cands = [
            p for p in header_pins("mcu") if p.name == c["mcu_pin"] and p.id not in used
        ]
        if not cands:
            raise PinConflict(
                f"No free {c['mcu_pin']} pin on the MCU for {c['part_ref']}.{c['part_pin']}: "
                f"two jumper wires can't share one header pin"
            )
        start = min(cands, key=lambda p: math.dist(p.position, end.position))
        used.add(start.id)
        pins[start.id], pins[end.id] = start, end
        hexc, name = wire_color(c, k)
        if name not in ("black", "red", "yellow", "blue"):
            k += 1
        wires.append(
            Wire(
                ref=f"w.{c['part_ref']}.{c['part_pin']}",
                part_ref=c["part_ref"],
                part_pin=c["part_pin"],
                mcu_pin=c["mcu_pin"],
                from_pin=start.id,
                to_pin=end.id,
                color=hexc,
                color_name=name,
            )
        )
    return Wiring(rev=SPEC_REV, pins=list(pins.values()), wires=wires)


# ------------------------------------------------------------------ instructions
WORD = {"beginner": "posts", "intermediate": "standoffs", "expert": "standoffs"}


def plan_steps(skill: str, layout: Layout, wiring: Wiring) -> list[Step]:
    order = mount_order()
    screws = {
        r: [o.ref for o in layout.objects if o.kind == "screw" and o.parent == r]
        for r in [*order, "lid"]
    }
    S: list[dict] = [
        {
            "id": "print",
            "kind": "print",
            "title": "Print the case",
            "actions": [Action(type="print", targets=["base", "lid"])],
        }
    ]
    if skill == "expert":
        S.append(
            {
                "id": "mount:all",
                "kind": "mount",
                "refs": order,
                "title": "Mount all boards",
                "actions": [
                    Action(type="place", targets=order),
                    Action(type="screw", targets=[s for r in order for s in screws[r]]),
                ],
            }
        )
    else:
        for r in order:
            sn = part(r).short_name
            if skill == "beginner":
                S.append(
                    {
                        "id": f"place:{r}",
                        "kind": "place",
                        "refs": [r],
                        "title": f"Place the {sn}",
                        "actions": [Action(type="place", targets=[r])],
                    }
                )
                S.append(
                    {
                        "id": f"screw:{r}",
                        "kind": "screw",
                        "refs": [r],
                        "title": f"Screw the {sn} down",
                        "actions": [Action(type="screw", targets=screws[r])],
                    }
                )
            else:
                S.append(
                    {
                        "id": f"mount:{r}",
                        "kind": "mount",
                        "refs": [r],
                        "title": f"Mount the {sn}",
                        "actions": [
                            Action(type="place", targets=[r]),
                            Action(type="screw", targets=screws[r]),
                        ],
                    }
                )
    wired = [r for r in order if any(w.part_ref == r for w in wiring.wires)]
    if skill == "expert":
        S.append(
            {
                "id": "wire:all",
                "kind": "wire",
                "refs": wired,
                "title": "Wire it up",
                "actions": [Action(type="wire", targets=[w.ref for w in wiring.wires])],
            }
        )
    else:
        for r in wired:
            S.append(
                {
                    "id": f"wire:{r}",
                    "kind": "wire",
                    "refs": [r],
                    "title": f"Connect the {part(r).short_name}",
                    "actions": [
                        Action(
                            type="wire",
                            targets=[w.ref for w in wiring.wires if w.part_ref == r],
                        )
                    ],
                }
            )
    S.append(
        {
            "id": "flash",
            "kind": "flash",
            "refs": ["mcu"],
            "title": "Plug in & upload the code",
            "actions": [
                Action(type="plug", targets=["usb"]),
                Action(type="flash", targets=["mcu"]),
            ],
        }
    )
    S.append(
        {
            "id": "lid",
            "kind": "lid",
            "refs": ["lid"],
            "title": "Close the lid",
            "actions": [
                Action(type="place", targets=["lid"]),
                Action(type="screw", targets=screws["lid"]),
            ],
        }
    )
    objs = {o.ref: o for o in layout.objects}
    wires = {w.ref: w for w in wiring.wires}
    out = []
    for n, s in enumerate(S, 1):
        focus = []
        for a in s["actions"]:
            for t in a.targets:
                if t in wires:
                    focus += [wires[t].part_ref, "mcu"]
                elif t in objs and objs[t].kind == "screw":
                    focus.append(objs[t].parent)
                else:
                    focus.append(t)
        out.append(
            Step(
                n=n,
                refs=s.get("refs", []),
                text=step_text(s, skill),
                needs=needs(s, objs, wires),
                focus=list(dict.fromkeys(focus)),
                **{k: s[k] for k in ("id", "kind", "title", "actions")},
            )
        )
    return out


def needs(s, objs, wires) -> list[Need]:
    out = []
    for a in s["actions"]:
        if a.type == "print":
            out += [Need(qty=1, label="base.stl"), Need(qty=1, label="lid.stl")]
            continue
        if a.type == "flash":
            out.append(Need(label="Ditto → Upload"))
            continue
        counts: dict[str, int] = {}
        for t in a.targets:
            if t in wires:
                lab = "jumper wires"
            else:
                o = objs[t]
                lab = {
                    "screw": "M2.5 screws",
                    "printed": "lid (printed)",
                    "cable": "USB cable",
                }.get(o.kind) or LIBRARY[o.part_id].short_name
            counts[lab] = counts.get(lab, 0) + 1
        out += [Need(qty=v, label=k) for k, v in counts.items()]
    return out


def step_text(s, skill) -> str:
    """Template text = the fallback. An optional LLM pass may rewrite it (never order or actions)."""
    B, X = skill == "beginner", skill == "expert"
    pt = part(s["refs"][0]) if s.get("refs") and s["refs"][0] in PL else None
    n = len(pt.mount_holes) if pt else 0
    usb = bool(pt and any(f["kind"] == "usb" for f in pt.features))
    k = s["kind"]
    if k == "print":
        return (
            (
                "Send base.stl and lid.stl to a 3D printer. Ditto already checked they fit your printer. "
                "It takes about 2 hours, so start this first."
            )
            if B
            else "base.stl + lid.stl · PLA · 0.2 mm · no supports."
            if X
            else "Print base.stl and lid.stl in PLA at 0.2 mm layers. No supports needed."
        )
    if k == "place":
        return (
            f"Set the {pt.short_name} on its {n} {WORD[skill]}"
            f"{', with the USB port facing the hole in the wall' if usb else ''}. {REASONS.get(s['refs'][0], '')}"
        ).strip()
    if k == "screw":
        return f"Add {n} small screws. Turn clockwise until snug. Too tight can crack the plastic posts."
    if k == "mount":
        return (
            "Seat each board on its standoffs, USB to the cutout. M2.5 screws, snug."
            if X
            else f"Seat the {pt.short_name} on its {n} standoffs{', USB toward the cutout' if usb else ''}, then {n}× M2.5 screws, snug only."
        )
    if k == "wire":
        return (
            (
                "Push each wire onto its pin until it clicks. Match the colors below. Each color has one job, "
                "so you can check your work at a glance."
            )
            if B
            else "Female–female jumpers per the pinout below."
            if X
            else "Female–female jumpers, colors as listed:"
        )
    if k == "flash":
        return (
            (
                "Plug the USB cable through the hole in the wall, then press Upload in Ditto. "
                "When the screen lights up, it worked!"
            )
            if B
            else "Flash over USB; expect 25:00 on boot."
            if X
            else "Connect USB and press Upload. The screen shows 25:00 when it boots."
        )
    if k == "lid":
        return (
            "Lay the lid on top with the window over the screen, then add the 4 corner screws."
            if B
            else "Lid on, 4× M2.5."
            if X
            else "Close the lid (window over the screen) and fit 4× M2.5 at the corners."
        )
    return s["title"]


def build_instructions(layout, wiring) -> Instructions:
    return Instructions(
        rev=SPEC_REV,
        skills={
            k: plan_steps(k, layout, wiring)
            for k in ("beginner", "intermediate", "expert")
        },
    )


# ------------------------------------------------------------------ checks (add to cross_checks)
def check_instructions(layout: Layout, wiring: Wiring, ins: Instructions) -> list[str]:
    errs, objs, wires = (
        [],
        {o.ref: o for o in layout.objects},
        {w.ref for w in wiring.wires},
    )
    for skill, steps in ins.skills.items():
        seen: dict[str, int] = {}
        for s in steps:
            for a in s.actions:
                for t in a.targets:
                    if t not in objs and t not in wires:
                        errs.append(f"[{skill}] step {s.n}: unknown ref {t}")
                    if a.type in ("place", "screw", "wire", "plug"):
                        seen[t] = seen.get(t, 0) + 1
        need_once = [
            r for r, o in objs.items() if o.kind in ("board", "screw", "cable")
        ] + ["lid", *wires]
        for r in need_once:
            if seen.get(r, 0) != 1:
                errs.append(
                    f"[{skill}] {r} is installed {seen.get(r, 0)} times (expected 1)"
                )
        kinds = [s.kind for s in steps]
        if kinds[-1] != "lid":
            errs.append(f"[{skill}] the lid must be the last step")
        if (
            "flash" in kinds
            and "wire" in kinds
            and kinds.index("flash")
            < max(i for i, k in enumerate(kinds) if k == "wire")
        ):
            errs.append(f"[{skill}] upload happens before all wires are connected")
    used = [w.from_pin for w in wiring.wires]
    if len(used) != len(set(used)):
        errs.append("two wires share one MCU header pin")
    return errs


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    layout = build_layout()
    wiring = build_wiring()
    ins = build_instructions(layout, wiring)
    problems = check_instructions(layout, wiring, ins)
    assert not problems, problems
    # round-trip through the contracts to prove the JSON validates
    for name, model, cls in [
        ("layout", layout, Layout),
        ("wiring", wiring, Wiring),
        ("instructions", ins, Instructions),
    ]:
        data = model.model_dump(mode="json")
        cls.model_validate(data)
        (out / f"{name}.json").write_text(json.dumps(data, indent=2))
    (out / "library.json").write_text(
        json.dumps({k: v.model_dump(mode="json") for k, v in LIBRARY.items()}, indent=2)
    )
    print(
        {k: len(v) for k, v in ins.skills.items()},
        "steps;",
        len(wiring.wires),
        "wires;",
        len(layout.objects),
        "objects",
    )
