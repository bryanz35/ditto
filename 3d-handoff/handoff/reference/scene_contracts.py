"""Scene contracts for the 3D viewer (proposed home: backend/contracts/scene.py).

These three files are the whole interface between the backend and the 3D instruction viewer:
  layout.json        -> Layout        (where every physical object is, in the web frame)
  wiring.json        -> Wiring        (which physical header pin each wire uses, and where it is)
  instructions.json  -> Instructions  (ordered steps for each skill level; refs only, no coordinates)

WEB FRAME: millimetres, Y-up, origin = centre of the case's bottom face.
  +x = right, +y = up, +z = toward the viewer ("front").
CAD FRAME (build123d): millimetres, Z-up, same origin. Convert with to_web(): (x, y, z) -> (x, z, -y).
So the CAD front wall (-y) becomes web +z, which faces the default camera.
"""

from typing import Literal

from pydantic import BaseModel, Field

Vec3 = tuple[float, float, float]
Skill = Literal["beginner", "intermediate", "expert"]


# ---------------------------------------------------------------- layout.json
class Dims(BaseModel):
    l: float  # along x
    w: float  # along z
    h: float  # along y


class Cutout(BaseModel):
    face: Literal[
        "front", "back", "left", "right"
    ]  # front=+z, back=-z, left=-x, right=+x
    for_ref: str  # e.g. "mcu.usb"
    center: tuple[
        float, float
    ]  # (along the wall, y). along = x for front/back, z for left/right
    size: tuple[float, float]  # (width along the wall, height)


class LidOpening(BaseModel):
    for_ref: str  # e.g. "oled1"
    shape: Literal["rect", "circle"]
    center_xz: tuple[float, float]
    size_xz: tuple[float, float] | None = None  # rect only
    r: float | None = None  # circle only


class Enclosure(BaseModel):
    template: Literal["box_lid"] = "box_lid"
    inner: Dims
    wall: float
    floor: float
    lid_thickness: float
    color: str = "#ffc83d"
    cutouts: list[Cutout] = []
    lid_openings: list[LidOpening] = []
    lid_screw_holes: list[tuple[float, float]] = []  # (x, z) on the lid
    standoffs: list[
        tuple[float, float, float]
    ] = []  # (x, z, top_y): printed posts under each board screw
    meshes: dict[
        Literal["base", "lid"], str
    ] = {}  # OPTIONAL GLB urls, same frame + mm. Viewer builds the case procedurally if absent.


class SceneObject(BaseModel):
    ref: str  # "base", "lid", "mcu", "oled1", "mcu.s1", "lid.s1", "usb"
    kind: Literal["printed", "board", "screw", "cable"]
    name: str  # shown in tooltips and the parts list
    reason: str = ""  # explain mode (boards copy PartInstance.reason)
    part_id: str | None = None  # boards: key into the parts library
    parent: str | None = None  # screws: the board/lid they hold down; boards: "base"
    position: Vec3  # boards: library origin at the board's bottom face
    # screws: where the head sits (top of the surface)
    # printed: base=(0,0,0); lid=its bottom face
    # cable: plug tip at the receptacle mouth
    local_to_world: list[float] | None = Field(None, min_length=16, max_length=16)
    # boards only: 4x4, COLUMN-MAJOR (three.js Matrix4.fromArray). Maps part-local (u, v, h) mm -> web world.
    # u = along board length from the library origin, v = along width, h = up from the board's bottom face.
    axis: Vec3 = (
        0.0,
        1.0,
        0.0,
    )  # screws: head-up direction. cable: direction the cable leaves the case.
    explode: Vec3 = (0.0, 0.0, 0.0)  # offset used by the exploded overview


class PrintItem(BaseModel):
    ref: str  # "base" | "lid"
    position: Vec3  # where it sits on the bed for the print animation
    flipped: bool = False  # lid printed top-face-down


class PrintLayout(BaseModel):
    bed_mm: tuple[float, float]  # from UserContext.printer
    items: list[PrintItem]


class Layout(BaseModel):
    rev: int
    units: Literal["mm"] = "mm"
    frame: Literal["web_y_up"] = "web_y_up"
    enclosure: Enclosure
    objects: list[SceneObject]
    print_layout: PrintLayout | None = None


# ---------------------------------------------------------------- wiring.json
class PinWorld(BaseModel):
    id: str  # "<part_ref>:<header_id>:<index>", e.g. "mcu:J3:0"
    part_ref: str
    name: str  # "GND", "GPIO21", "SDA"
    position: Vec3  # pin TIP, web frame
    dir: Literal[1, -1]  # +1 pin points up (+y), -1 points down


class Wire(BaseModel):
    ref: str  # "w.<part_ref>.<part_pin>", e.g. "w.oled1.SDA"
    part_ref: str  # copied from spec Connection
    part_pin: str
    mcu_pin: str  # logical name from the spec ("GND")
    from_pin: str  # PinWorld.id on the MCU (the physical pin the allocator chose)
    to_pin: str  # PinWorld.id on the part
    color: str  # hex
    color_name: str  # "black" (shown to beginners)
    kind: Literal["jumper_ff", "jumper_mf", "qwiic"] = "jumper_ff"


class Wiring(BaseModel):
    rev: int
    pins: list[PinWorld]  # every pin referenced by a wire
    wires: list[Wire]


# ---------------------------------------------------------------- library.json (GET /api/parts/library.json)
# The viewer draws each board procedurally from these fields. Coordinates are PART-LOCAL (u, v, h) in mm,
# using the same origin your YAML already uses for mount_holes/features (board corner per PROJECT_PLAN).
class BoardDims(BaseModel):
    l: float  # along u
    w: float  # along v
    h: float  # PCB thickness


class Header(BaseModel):
    id: str  # "J2", "J3", "H1"
    origin: tuple[float, float]  # (u, v) of pin index 0
    pitch: tuple[float, float]  # (du, dv) step to the next pin, e.g. (2.54, 0)
    side: Literal["top", "bottom"] = "top"  # which way the pins point
    pin_len_mm: float = 6.0
    pins: list[
        str
    ]  # names in physical order; MCU names MUST match spec mcu_pin strings ("GPIO21", "3V3", "GND")


class LookShape(BaseModel):  # optional cosmetic shapes on top of the PCB
    shape: Literal["box", "cyl", "led", "screen"]
    at: tuple[float, float]  # (u, v) centre
    size: tuple[float, float, float] | None = (
        None  # box/led: (su, sv, sh). screen: (su, sv, 0); text "up" is +v
    )
    r: float | None = None  # cyl
    h: float | None = None  # cyl height
    color: str | None = None
    metal: float = 0.0


class ViewerPart(BaseModel):
    id: str
    name: str
    short_name: str  # kid-friendly noun used in step text: "screen", "beeper"
    category: str
    board_mm: BoardDims
    pcb_color: str = "#1f4e9c"
    mount_holes: list[tuple[float, float]]
    features: list[dict] = []  # as in the YAML (usb, display_window, sound_port, ...)
    headers: list[Header] = []
    look: list[LookShape] = []
    price_usd: float | None = None


# ---------------------------------------------------------------- instructions.json
ActionType = Literal["print", "place", "screw", "wire", "plug", "flash", "highlight"]
# "highlight" = generic fallback (pulse the targets) for any step that has no dedicated animation yet.


class Action(BaseModel):
    type: ActionType
    targets: list[str]  # refs from layout.objects or wiring.wires, played in order


class Need(BaseModel):
    qty: int | None = None
    label: str  # "M2.5 screws", "jumper wires", "base.stl"


class Step(BaseModel):
    id: str  # stable: "print", "place:mcu", "screw:mcu", "mount:mcu", "wire:oled1", "flash", "lid"
    n: int  # 1-based
    kind: Literal["print", "place", "screw", "mount", "wire", "flash", "lid"]
    refs: list[str] = []  # the main part(s) of the step
    title: str
    text: str
    needs: list[Need] = []  # the LEGO-style "you need" box
    actions: list[Action]
    focus: list[str] = []  # refs the camera should frame


class Instructions(BaseModel):
    rev: int  # spec rev these steps were built from
    text_rev: int = 0  # bumps when the LLM rewrites text; order/actions unchanged
    skills: dict[Skill, list[Step]]
