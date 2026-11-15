// The device in the 3D view: case, parts, wires, and their animations (overview explode, build steps).
// Built from assembly.glb (case, lid, a custom device's extra printed parts, and one box per inside or
// mounted part, named by ref) plus the spec and wiring.json: each box becomes a part model (parts.ts),
// each wiring row a jumper wire, routed round the parts and the case (route.ts).
// Frame: the enclosure's (mm, Z up); z = 0 is the cavity floor.
import {
  Box3,
  BoxGeometry,
  CatmullRomCurve3,
  ConeGeometry,
  CylinderGeometry,
  DoubleSide,
  EdgesGeometry,
  Group,
  LineBasicMaterial,
  LineSegments,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  Plane,
  Quaternion,
  TubeGeometry,
  Vector2,
  Vector3,
  type Material,
  type Object3D,
} from 'three'
import type { EnclosureManifest, ProjectSpec, Wiring, WiringRow } from '../contracts'
import { buildPart, categoryOf, LIBRARY, pinsOf, type Category, type PartModel } from './parts'
import { route, shell, solid, WIRE_R, type Route, type RouteOptions } from './route'

/** The bits of a build step the scene animates (guide.ts's Step has them). */
export interface SceneStep {
  kind: 'Print' | 'Place' | 'Assemble' | 'Wiring' | 'Code' | 'Close'
  /** The part placed or wired (a ref), or the printed part fitted (its name). */
  ref: string | null
}

// index.css --color-wire-*, by guide.ts's WIRE_COLOURS (black is lifted a little to read on the dark view)
const WIRE_HEX: Record<WiringRow['pin_type'], string> = {
  power: '#e5534b',
  gnd: '#2a2b30',
  i2c_scl: '#eab308',
  i2c_sda: '#3b82f6',
  analog: '#22c55e',
  gpio: '#f97316',
  gpio_in: '#f97316',
  gpio_out: '#f97316',
  spi_sck: '#a855f7',
  spi_mosi: '#a855f7',
  spi_miso: '#a855f7',
  spi_cs: '#a855f7',
  uart_tx: '#f5f5f5',
  uart_rx: '#f5f5f5',
  i2s_bclk: '#14b8a6',
  i2s_ws: '#14b8a6',
  i2s_din: '#14b8a6',
  i2s_dout: '#14b8a6',
  config: '#8b8b8b',
}
const ACCENT = '#b78ad0'
const CASE = '#55555d'
const CASE_EDGE = '#8d8d96'
const LID_DROP = 45

interface PartEntry {
  ref: string
  partId: string
  inside: boolean
  model: PartModel
  holder: Group
  home: Vector3
  /** How the part is turned where it sits (a mounted part can be on its side). */
  turn: Quaternion
  explode: Vector3
  size: Vector3
  outline: LineSegments<EdgesGeometry, LineBasicMaterial>
}

interface WireEntry {
  row: WiringRow
  group: Group
  tube: Mesh<TubeGeometry>
  count: number
  ends: [Mesh, Mesh]
  /** What the wire still runs into (route.ts found no clean path): [] normally. */
  hits: string[]
}

const ease = (t: number) => 1 - Math.pow(1 - Math.min(1, Math.max(0, t)), 3)
const clamp01 = (t: number) => Math.min(1, Math.max(0, t))

export class Device {
  /** The device: case, lid, parts and wires (the camera frames this). */
  readonly root = new Group()
  /** Step props that come and go (USB cable, printer nozzle, arrow): not clickable, not framed. */
  readonly extras = new Group()
  /** Invisible box around the assembled and exploded device: hovering it explodes the overview. */
  readonly proxy: Mesh
  /** Invisible box the overview's camera frames: the device, and its parts exploded (not the lid). */
  readonly frame: Mesh
  readonly parts = new Map<string, PartEntry>()
  /** A custom device's extra printed parts by name, where they sit once assembled. */
  readonly printed = new Map<string, { mesh: Mesh; home: Vector3; box: Box3 }>()
  private wires: WireEntry[] = []
  private base: Mesh
  private baseMat: MeshStandardMaterial
  private lid: Group | null = null
  private lidMat: MeshStandardMaterial | null = null
  private lidHome = new Vector3()
  private lidExplode = new Vector3()
  private lidScrews: Group[] = []
  private usb: Group | null = null
  private usbDir = new Vector3()
  private usbHome = new Vector3()
  private lidTopZ = 0
  private nozzle: Group
  private arrow: Group
  private arrowMat: MeshBasicMaterial
  private clip = new Plane(new Vector3(0, 0, -1), 1e4)
  private caseBox = new Box3()
  private mcuRef: string | null = null
  /** Underside of the case: where the floor grid goes (the cavity floor is z = 0). */
  readonly groundZ: number
  private owned: (Material | { dispose: () => void })[] = []

  // state
  private mode: 'overview' | 'build' = 'overview'
  private explodeTarget = 0
  private explode = 0
  private hovering = false
  private hoverRef: string | null = null
  private selectedRef: string | null = null
  private step: SceneStep | null = null
  private placed = new Set<string>()
  private fitted = new Set<string>()
  private wired = new Set<string>()
  private stepClock = 0

  constructor(
    glb: Object3D,
    spec: ProjectSpec | null,
    wiring: Wiring | null,
    manifest: EnclosureManifest | null = null,
  ) {
    glb.updateMatrixWorld(true)
    const rows = wiring?.rows ?? []
    const instances = spec ? [...(spec.mcu ? [spec.mcu] : []), ...spec.parts] : []
    const partIdOf = new Map(instances.map((p) => [p.ref, p.part_id]))
    const custom = new Map((spec?.custom_parts ?? []).map((p) => [p.id, p]))
    const catOf = (id: string): Category => (LIBRARY[id] ? categoryOf(id) : (custom.get(id)?.category ?? 'sensor'))
    this.mcuRef = spec?.mcu?.ref ?? null

    // case
    const meshIn = (name: string) => {
      let found: Mesh | undefined
      glb.getObjectByName(name)?.traverse((o) => {
        if (!found && o instanceof Mesh) found = o
      })
      return found
    }
    const baseNode = meshIn('base')
    const lidNode = meshIn('lid')
    this.baseMat = new MeshStandardMaterial({
      color: CASE,
      roughness: 0.8,
      side: DoubleSide,
      clippingPlanes: [this.clip],
    })
    this.base = new Mesh(baseNode ? baseNode.geometry.clone() : new BoxGeometry(1, 1, 1), this.baseMat)
    if (baseNode) this.base.applyMatrix4(baseNode.matrixWorld)
    this.base.name = 'base'
    // what the wires must not pass through (named for route.ts's hit list)
    const shells: Mesh[] = [this.base]
    this.base.add(
      new LineSegments(
        new EdgesGeometry(this.base.geometry, 30),
        new LineBasicMaterial({
          color: CASE_EDGE,
          transparent: true,
          opacity: 0.5,
          clippingPlanes: [this.clip],
        }),
      ),
    )
    this.root.add(this.base)
    this.caseBox.setFromObject(this.base)
    this.groundZ = this.caseBox.min.z
    const caseTop = this.caseBox.max.z
    if (lidNode) {
      // the lid STL is in its closed position; assembly.glb only lifts its node
      this.lidMat = new MeshStandardMaterial({
        color: CASE,
        roughness: 0.8,
        side: DoubleSide,
        transparent: true,
        opacity: 0.3,
        depthWrite: false,
      })
      const lid = new Mesh(lidNode.geometry.clone(), this.lidMat)
      lid.name = 'lid'
      shells.push(lid)
      lid.add(
        new LineSegments(
          new EdgesGeometry(lid.geometry, 30),
          new LineBasicMaterial({
            color: CASE_EDGE,
            transparent: true,
            opacity: 0.45,
          }),
        ),
      )
      this.lid = new Group()
      this.lid.add(lid)
      this.root.add(this.lid)
      const lb = new Box3().setFromObject(lid)
      this.lidTopZ = lb.max.z
      for (const [sx, sy] of [
        [1, 1],
        [-1, 1],
        [1, -1],
        [-1, -1],
      ]) {
        const s = screw(this.std('#b9bec6', 0.75))
        s.position.set(sx > 0 ? lb.max.x - 4 : lb.min.x + 4, sy > 0 ? lb.max.y - 4 : lb.min.y + 4, lb.max.z)
        this.lid.add(s)
        this.lidScrews.push(s)
      }
    }

    // extra printed parts (glb nodes "print_<name>"), already where they sit once assembled
    glb.traverse((o) => {
      if (!(o instanceof Mesh) || !o.userData.printed) return
      const m = new Mesh(o.geometry.clone(), this.baseMat)
      m.applyMatrix4(o.matrixWorld)
      m.add(
        new LineSegments(
          new EdgesGeometry(m.geometry, 30),
          new LineBasicMaterial({ color: CASE_EDGE, transparent: true, opacity: 0.5, clippingPlanes: [this.clip] }),
        ),
      )
      this.root.add(m)
      m.name = o.name.replace(/^print_/, '')
      shells.push(m)
      this.printed.set(o.name.replace(/^print_/, ''), { mesh: m, home: m.position.clone(), box: new Box3().setFromObject(m) })
    })

    // inside parts and mounted ones: one box per ref in assembly.glb
    const boxes: {
      ref: string
      partId: string
      center: Vector3
      size: Vector3
      turn: Quaternion
      mounted: boolean
    }[] = []
    glb.traverse((o) => {
      if (!(o instanceof Mesh) || o === baseNode || o === lidNode || boxes.some((b) => b.ref === o.name)) return
      const geo = o.geometry
      geo.computeBoundingBox()
      const bb = geo.boundingBox as Box3
      const partId = (o.userData.part_id as string | undefined) ?? partIdOf.get(o.name)
      if (!partId) return
      boxes.push({
        ref: o.name,
        partId,
        center: o.localToWorld(bb.getCenter(new Vector3())),
        size: bb.getSize(new Vector3()),
        turn: o.getWorldQuaternion(new Quaternion()),
        mounted: typeof o.userData.mounted_on === 'string',
      })
    })
    if (!this.mcuRef) this.mcuRef = boxes.find((b) => catOf(b.partId) === 'mcu')?.ref ?? null
    const mcuBox = boxes.find((b) => b.ref === this.mcuRef)
    const caseCenter = this.caseBox.getCenter(new Vector3())

    const add = (
      ref: string,
      partId: string,
      center: Vector3,
      size: Vector3,
      inside: boolean,
      toward: Vector2,
      turn = new Quaternion(),
    ) => {
      const used = rows.filter((r) => r.part_ref === ref).map((r) => r.part_pin)
      const mcuUsed = ref === this.mcuRef ? rows.map((r) => r.mcu_pin) : []
      const lib = LIBRARY[partId]
      const pins =
        custom.has(partId) && !lib
          ? [...(custom.get(partId)?.pins.map((p) => p.name) ?? []), ...used]
          : pinsOf(partId, [...used, ...mcuUsed])
      const model = buildPart(partId, catOf(partId), size, toward, [...new Set(pins)], custom.get(partId))
      const holder = new Group()
      holder.position.copy(center)
      holder.quaternion.copy(turn)
      holder.add(model.root)
      holder.userData.ref = ref
      const outline = new LineSegments(
        new EdgesGeometry(new BoxGeometry(size.x + 2, size.y + 2, size.z + 2)),
        new LineBasicMaterial({
          color: ACCENT,
          transparent: true,
          opacity: 1,
          depthTest: false,
        }),
      )
      outline.renderOrder = 10
      outline.visible = false
      outline.raycast = () => {}
      holder.add(outline)
      this.root.add(holder)
      this.parts.set(ref, {
        ref,
        partId,
        inside,
        model,
        holder,
        home: center.clone(),
        turn,
        explode: new Vector3(),
        size,
        outline,
      })
    }

    const towardMcu = (c: Vector3) =>
      mcuBox ? new Vector2(mcuBox.center.x - c.x, mcuBox.center.y - c.y).normalize() : new Vector2(0, -1)
    const towardWall = (c: Vector3) => {
      const d = [
        [c.x - this.caseBox.min.x, -1, 0],
        [this.caseBox.max.x - c.x, 1, 0],
        [c.y - this.caseBox.min.y, 0, -1],
        [this.caseBox.max.y - c.y, 0, 1],
      ].sort((a, b) => a[0] - b[0])[0]
      return new Vector2(d[1], d[2])
    }
    for (const b of boxes) {
      const toward = b.ref === this.mcuRef ? towardWall(b.center) : b.mounted ? new Vector2(0, -1) : towardMcu(b.center)
      add(b.ref, b.partId, b.center, b.size, !b.mounted, toward, b.turn)
    }

    // parts outside the case (mounting: external) have no box: lay them on the floor behind it, pins
    // towards the case (behind, they don't hide the inside from the default camera)
    let y = this.caseBox.max.y + 12
    for (const p of spec?.parts ?? []) {
      if (this.parts.has(p.ref)) continue
      const def = custom.get(p.part_id)
      const mm = LIBRARY[p.part_id]?.mm ?? (def ? [def.board_mm.l, def.board_mm.w, def.board_mm.h] : [25, 20, 8])
      const size = new Vector3(Math.max(mm[0], mm[1]), Math.min(mm[0], mm[1]), mm[2])
      const center = new Vector3(caseCenter.x, y + size.y / 2, this.caseBox.min.z + size.z / 2)
      y += size.y + 10
      add(p.ref, p.part_id, center, size, false, new Vector2(0, -1))
    }

    // exploded view: each part lifts (in order, the board lowest) and spreads out from the middle
    let rank = 0
    let top = 0
    for (const e of [...this.parts.values()].sort((a, b) =>
      a.ref === this.mcuRef ? -1 : b.ref === this.mcuRef ? 1 : 0,
    )) {
      if (!e.inside) {
        e.explode.set(18, 0, 8)
        continue
      }
      const spread = new Vector3(e.home.x - caseCenter.x, e.home.y - caseCenter.y, 0).multiplyScalar(0.45)
      e.explode.set(spread.x, spread.y, 26 + 11 * rank++)
      top = Math.max(top, e.explode.z + e.size.z)
    }
    this.lidExplode.set(0, 0, top + 18)

    // wires: a jumper per wiring row, from the board's pin to the part's pin, round whatever is between
    this.root.updateMatrixWorld(true)
    const obs = {
      solids: [...this.parts.values()].map((e) => solid(e.ref, e.home, e.turn, e.size)),
      shells: shells.map(shell),
    }
    const mounted = new Set(boxes.filter((b) => b.mounted).map((b) => b.ref))
    const wall = manifest?.wall_mm ?? 2
    // under the lid: the cavity's height (a custom body's own top can be far above where the parts are)
    const ceiling = (manifest?.cavity_mm[2] ?? caseTop) - 1.5
    const mcu = this.mcuRef ? this.parts.get(this.mcuRef) : undefined
    const taken = new Set<string>()
    const worldPin = (e: PartEntry, at: Vector3) => at.clone().applyQuaternion(e.turn).add(e.home)
    const byPart = new Map<string, number>()
    for (const row of rows) {
      const part = this.parts.get(row.part_ref)
      if (!part || !mcu) continue
      const pp = part.model.pins.find((p) => p.name === row.part_pin)
      if (!pp) continue
      const to = worldPin(part, pp.at)
      // "GND" may be any of several header pins: take the nearest one still free
      const cands = mcu.model.pins
        .map((p, i) => ({ p, i, w: worldPin(mcu, p.at) }))
        .filter((c) => c.p.name === row.mcu_pin)
        .sort(
          (a, b) =>
            Number(taken.has(`${a.i}`)) - Number(taken.has(`${b.i}`)) || a.w.distanceTo(to) - b.w.distanceTo(to),
        )
      const from = cands[0]?.w ?? mcu.home.clone().setZ(mcu.home.z + mcu.size.z / 2)
      if (cands[0]) taken.add(`${cands[0].i}`)
      const k = byPart.get(row.part_ref) ?? 0
      byPart.set(row.part_ref, k + 1)
      const opts: RouteOptions = { spread: (k - 1.5) * 1.6, ceiling, own: [mcu.ref, part.ref] }
      if (!part.inside) {
        // an outside part (laid behind the case, or mounted on a custom device's prints): out through
        // the cable hole build_enclosure cuts for it in the back wall
        const c = manifest?.cutouts.find(
          (c) => c.feature === 'cable' && c.face === 'back' && c.for_ref === row.part_ref,
        )
        const y = manifest ? manifest.cavity_mm[1] + wall / 2 : this.caseBox.max.y - wall / 2
        const out = new Vector3(0, 1, 0)
        if (c) {
          opts.hole = { at: new Vector3(c.center_mm[0], y, c.center_mm[1]), dir: out, depth: wall, size: c.size_mm[0] }
        } else if (mounted.has(row.part_ref)) {
          // no hole: it sits on the shell, so its cable goes through right there
          opts.allow = obs.solids.find((s) => s.name === row.part_ref)?.aabb.clone().expandByScalar(3)
          opts.ignore = [row.part_ref]
        } else {
          // an old manifest (or none): through the back wall about where build_enclosure puts the hole
          const x = Math.min(this.caseBox.max.x - wall - 4, Math.max(this.caseBox.min.x + wall + 4, to.x))
          opts.hole = { at: new Vector3(x, y, caseTop / 2), dir: out, depth: wall, size: 6 }
          opts.allow = new Box3().setFromCenterAndSize(opts.hole.at, new Vector3(10, wall + 4, 10))
          if (import.meta.env.DEV) console.warn(`[wires] no cable hole for ${row.part_ref} in cad/manifest.json`)
        }
      }
      const r = route(from, to, obs, opts)
      if (import.meta.env.DEV && r.hits.length)
        console.warn(`[wires] ${this.mcuRef}.${row.mcu_pin} → ${row.part_ref}.${row.part_pin} clips ${r.hits.join(', ')}`)
      this.wires.push(this.buildWire(row, from, to, r))
    }

    // USB cable for the code step: plug from the board's socket out through the nearest wall
    if (mcu?.model.usb) {
      const at = mcu.model.usb.at.clone().add(mcu.home)
      const dir = mcu.model.usb.dir.clone()
      this.usbDir.copy(dir)
      const wall =
        dir.x > 0.5
          ? this.caseBox.max.x - at.x
          : dir.x < -0.5
            ? at.x - this.caseBox.min.x
            : dir.y > 0.5
              ? this.caseBox.max.y - at.y
              : at.y - this.caseBox.min.y
      const g = new Group()
      const metal = new Mesh(new BoxGeometry(wall + 2, 7, 2.4), this.std('#c9ccd2', 0.6))
      metal.position.set((wall + 2) / 2, 0, 0)
      const boot = new Mesh(new BoxGeometry(13, 11, 7), this.std('#2b2d31'))
      boot.position.set(wall + 2 + 6.5, 0, 0)
      const groundZ = this.caseBox.min.z - at.z + 1.6
      const pts = [
        [wall + 13, 0, 0],
        [wall + 22, 0, 0],
        [wall + 34, 4, groundZ * 0.5],
        [wall + 50, 10, groundZ],
        [wall + 70, 14, groundZ],
      ].map(([x, y, z]) => new Vector3(x, y, z))
      const cable = new Mesh(new TubeGeometry(new CatmullRomCurve3(pts), 60, 1.6, 10), this.std('#2b2d31'))
      g.add(metal, boot, cable)
      g.position.copy(at)
      this.usbHome.copy(at)
      g.rotation.z = Math.atan2(dir.y, dir.x)
      g.visible = false
      this.usb = g
      this.extras.add(g)
    }

    // helpers: the printer nozzle (print step) and the arrow over a part being placed
    this.nozzle = new Group()
    const tip = new Mesh(new ConeGeometry(2.2, 4, 18).rotateX(-Math.PI / 2), this.std('#d4a640', 0.6))
    tip.position.z = 2
    const head = new Mesh(new BoxGeometry(12, 12, 9), this.std('#c9ccd2', 0.5))
    head.position.z = 8.5
    this.nozzle.add(tip, head)
    this.nozzle.visible = false
    this.arrowMat = new MeshBasicMaterial({
      color: ACCENT,
      transparent: true,
      depthTest: false,
    })
    this.owned.push(this.arrowMat)
    this.arrow = new Group()
    const cone = new Mesh(new ConeGeometry(4, 7, 24).rotateX(-Math.PI / 2), this.arrowMat)
    cone.position.z = 3.5
    const shaft = new Mesh(new CylinderGeometry(1.5, 1.5, 11, 16).rotateX(Math.PI / 2), this.arrowMat)
    shaft.position.z = 12.5
    this.arrow.add(cone, shaft)
    this.arrow.renderOrder = 11
    this.arrow.visible = false
    this.extras.add(this.nozzle, this.arrow)
    this.extras.traverse((c) => (c.raycast = () => {}))

    // camera frame: assembled and exploded extents together; the hover target adds the raised lid
    const all = new Box3().setFromObject(this.root)
    for (const e of this.parts.values())
      all.union(new Box3().setFromCenterAndSize(e.home.clone().add(e.explode), e.size))
    this.frame = new Mesh(
      new BoxGeometry(...all.getSize(new Vector3()).toArray()),
      new MeshBasicMaterial({ visible: false }),
    )
    this.frame.position.copy(all.getCenter(new Vector3()))
    this.frame.raycast = () => {}
    this.owned.push(this.frame.material as Material, this.frame.geometry)
    if (this.lid) all.expandByPoint(this.caseBox.max.clone().add(this.lidExplode))
    this.proxy = new Mesh(
      new BoxGeometry(...all.getSize(new Vector3()).toArray()),
      new MeshBasicMaterial({ visible: false }),
    )
    this.proxy.position.copy(all.getCenter(new Vector3()))
    this.owned.push(this.proxy.material as Material)

    this.setOverview(false)
  }

  private std(color: string, metal = 0) {
    const m = new MeshStandardMaterial({
      color,
      roughness: metal ? 0.35 : 0.6,
      metalness: metal,
    })
    this.owned.push(m)
    return m
  }

  private buildWire(row: WiringRow, from: Vector3, to: Vector3, r: Route): WireEntry {
    const g = new Group()
    const tube = new Mesh(new TubeGeometry(r.curve, 90, WIRE_R, 8, false), this.std(WIRE_HEX[row.pin_type] ?? '#8b8b8b'))
    const housing = (p: Vector3) => {
      const m = new Mesh(new BoxGeometry(2.5, 2.5, 6), this.std('#151618'))
      m.position.copy(p).setZ(p.z - 1)
      return m
    }
    const ends: [Mesh, Mesh] = [housing(from), housing(to)]
    g.add(tube, ...ends)
    g.userData.wire = `${row.part_ref}.${row.part_pin}`
    this.root.add(g)
    return {
      row,
      group: g,
      tube,
      count: tube.geometry.index?.count ?? 0,
      ends,
      hits: r.hits,
    }
  }

  /** What each wire ("ref.pin") still runs into: all [] when every wire found a clean path. */
  wireClips(): Record<string, string[]> {
    return Object.fromEntries(this.wires.map((w) => [`${w.row.part_ref}.${w.row.part_pin}`, w.hits]))
  }

  /** Overview: everything in place, lid see-through; `exploded` holds the parts apart. */
  setOverview(exploded: boolean) {
    this.mode = 'overview'
    this.step = null
    this.explodeTarget = exploded ? 1 : 0
    this.lockExploded = exploded
  }

  private lockExploded = false

  setHover(on: boolean) {
    this.hovering = on
  }

  setHoverPart(ref: string | null) {
    this.hoverRef = ref
  }

  setSelected(ref: string | null) {
    this.selectedRef = ref
  }

  /** Build guide: the scene as it is during `steps[index]`, with that step's animation looping. */
  setBuild(steps: SceneStep[], index: number) {
    this.mode = 'build'
    this.step = steps[index] ?? null
    const before = steps.slice(0, index)
    this.placed = new Set(before.filter((s) => s.kind === 'Place' && s.ref).map((s) => s.ref as string))
    this.wired = new Set(before.filter((s) => s.kind === 'Wiring' && s.ref).map((s) => s.ref as string))
    this.fitted = new Set(before.filter((s) => s.kind === 'Assemble' && s.ref).map((s) => s.ref as string))
    // a part no step places (or printed part no step fits) is just there
    const mentioned = new Set(steps.filter((s) => s.kind === 'Place').map((s) => s.ref))
    for (const ref of this.parts.keys()) if (!mentioned.has(ref)) this.placed.add(ref)
    const fits = new Set(steps.filter((s) => s.kind === 'Assemble').map((s) => s.ref))
    for (const name of this.printed.keys()) if (!fits.has(name)) this.fitted.add(name)
    if (this.step && (this.step.kind === 'Code' || this.step.kind === 'Close')) {
      for (const ref of this.parts.keys()) this.placed.add(ref)
      for (const name of this.printed.keys()) this.fitted.add(name)
      for (const w of this.wires) this.wired.add(w.row.part_ref)
    }
    this.stepClock = 0
    this.explode = 0
    this.explodeTarget = 0
  }

  /** Restart the current step's animation. */
  replay() {
    this.stepClock = 0
  }

  /** Where a part's label goes: just over its top, wherever it is right now. */
  anchorOf(ref: string): Vector3 | null {
    const p = this.printed.get(ref)
    if (p && !this.parts.has(ref)) {
      if (!p.mesh.visible) return null
      return p.box.getCenter(new Vector3()).setZ(p.box.max.z + 3 + p.mesh.position.z - p.home.z)
    }
    const e = this.parts.get(ref)
    if (!e || !e.holder.visible) return null
    return e.holder.position.clone().setZ(e.holder.position.z + e.size.z / 2 + 3)
  }

  /** The part ref an object in the scene belongs to, if any. */
  refOf(o: Object3D | null): string | null {
    for (let n = o; n; n = n.parent) if (typeof n.userData.ref === 'string') return n.userData.ref
    return null
  }

  update(dt: number) {
    if (this.mode === 'overview') this.updateOverview(dt)
    else this.updateBuild(dt)
  }

  private ghost(on: boolean) {
    this.baseMat.transparent = on
    this.baseMat.opacity = on ? 0.4 : 1
    this.baseMat.depthWrite = !on
  }

  private drawWire(w: WireEntry, t: number) {
    const n = Math.floor((w.count * clamp01(t)) / 3) * 3
    w.tube.geometry.setDrawRange(0, n)
    w.ends[0].visible = t > 0
    w.ends[1].visible = t >= 0.98
  }

  private power(state: 'off' | 'upload' | 'on', p = 0) {
    // screens show the upload's progress, like the spike (a real one stays dark until the code runs)
    for (const e of this.parts.values()) e.model.setPower(state, p)
  }

  private updateOverview(dt: number) {
    const target = this.lockExploded || this.hovering ? 1 : 0
    this.explodeTarget = target
    this.explode += (this.explodeTarget - this.explode) * (1 - Math.exp(-dt * 6))
    const x = ease(this.explode)
    this.clip.constant = 1e4
    this.ghost(false)
    this.nozzle.visible = false
    this.arrow.visible = false
    if (this.usb) this.usb.visible = false
    for (const p of this.printed.values()) {
      p.mesh.visible = true
      p.mesh.position.copy(p.home)
    }
    for (const e of this.parts.values()) {
      e.holder.visible = true
      e.holder.quaternion.copy(e.turn)
      e.holder.position.copy(e.home).addScaledVector(e.explode, x)
      e.outline.visible = e.ref === this.selectedRef || e.ref === this.hoverRef
      e.outline.material.opacity = e.ref === this.selectedRef ? 1 : 0.5
    }
    for (const w of this.wires) {
      w.group.visible = this.explode < 0.04
      this.drawWire(w, 1)
    }
    if (this.lid && this.lidMat) {
      this.lid.visible = true
      this.lid.position.copy(this.lidHome).addScaledVector(this.lidExplode, x)
      this.lidMat.opacity = 0.3
      this.lidMat.transparent = true
      this.lidMat.depthWrite = false
      for (const s of this.lidScrews) {
        s.visible = this.explode < 0.04
        s.position.z = this.lidTopZ
        s.rotation.z = 0
      }
    }
    this.power('on')
  }

  private updateBuild(dt: number) {
    const step = this.step
    if (!step) return
    this.stepClock += dt
    const DUR: Record<SceneStep['kind'], number> = {
      Print: 4,
      Place: 1.2,
      Assemble: 1.2,
      Wiring: Math.max(1, this.wires.filter((w) => w.row.part_ref === step.ref).length * 0.75),
      Code: 3.2,
      Close: 2.2,
    }
    const period = DUR[step.kind] + (step.kind === 'Code' ? 2.6 : 1.8)
    const t = this.stepClock % period
    const now = this.stepClock

    this.clip.constant = 1e4
    this.nozzle.visible = false
    this.arrow.visible = false
    this.ghost(step.kind === 'Place' || step.kind === 'Wiring' || step.kind === 'Code')

    // parts: placed ones sit at home; the step's part drops in
    for (const e of this.parts.values()) {
      const current = step.kind === 'Place' && step.ref === e.ref
      e.holder.visible = step.kind !== 'Print' && (this.placed.has(e.ref) || current)
      e.holder.position.copy(e.home)
      e.holder.quaternion.copy(e.turn)
      const focus = step.ref === e.ref && step.kind !== 'Code'
      e.outline.visible = focus
      e.outline.material.opacity = 0.55 + 0.45 * Math.abs(Math.sin(now * 2.4))
      if (current) {
        const k = ease(t / DUR.Place)
        const lift = 40 * (1 - k)
        if (e.inside) e.holder.position.z += lift
        else e.holder.position.x += lift
        e.holder.rotateZ(0.4 * (1 - k))
        this.arrow.visible = t < DUR.Place
        this.arrowMat.opacity = t < 0.7 ? 1 : 1 - (t - 0.7) / 0.5
        this.arrow.position.set(
          e.holder.position.x,
          e.holder.position.y,
          e.holder.position.z + e.size.z / 2 + 6 + 2 * Math.sin(now * 8),
        )
      }
    }

    // printed parts: fitted ones sit at home; the step's part drops onto what holds it
    for (const [name, p] of this.printed) {
      const current = step.kind === 'Assemble' && step.ref === name
      p.mesh.visible = step.kind !== 'Print' && (this.fitted.has(name) || current)
      p.mesh.position.copy(p.home)
      if (current) {
        const k = ease(t / DUR.Assemble)
        p.mesh.position.z += 40 * (1 - k)
        this.arrow.visible = t < DUR.Assemble
        this.arrowMat.opacity = t < 0.7 ? 1 : 1 - (t - 0.7) / 0.5
        const c = p.box.getCenter(new Vector3())
        this.arrow.position.set(c.x, c.y, p.box.max.z + 40 * (1 - k) + 6 + 2 * Math.sin(now * 8))
      }
    }

    // wires: earlier steps' are in; the step's own are pushed on one after another
    const mine = this.wires.filter((w) => step.kind === 'Wiring' && w.row.part_ref === step.ref)
    for (const w of this.wires) {
      const i = mine.indexOf(w)
      if (i >= 0) {
        w.group.visible = true
        this.drawWire(w, (t - i * 0.75) / 0.7)
      } else {
        w.group.visible = this.wired.has(w.row.part_ref)
        this.drawWire(w, 1)
      }
    }

    // USB and power
    if (this.usb) {
      this.usb.visible = step.kind === 'Code' || step.kind === 'Close'
      const k = step.kind === 'Code' ? ease(t / 0.9) : 1
      this.usb.position.copy(this.usbHome).addScaledVector(this.usbDir, 30 * (1 - k))
    }
    if (step.kind === 'Code') {
      const p = clamp01((t - 1) / (DUR.Code - 1))
      if (t < 1) this.power('off')
      else if (p < 1) this.power('upload', p)
      else this.power('on')
    } else this.power(step.kind === 'Close' ? 'on' : 'off')

    // lid
    if (this.lid && this.lidMat) {
      this.lid.visible = step.kind === 'Close'
      this.lidMat.transparent = false
      this.lidMat.opacity = 1
      this.lidMat.depthWrite = true
      const k = ease(t / 1.1)
      this.lid.position.copy(this.lidHome).setZ(this.lidHome.z + LID_DROP * (1 - k))
      this.lidScrews.forEach((s, i) => {
        const ks = ease((t - 1.1 - i * 0.12) / 0.8)
        s.visible = t > 1.1 + i * 0.12
        s.position.z = this.lidTopZ + 8 * (1 - ks)
        s.rotation.z = -ks * Math.PI * 6
      })
    }

    // printing: the base grows layer by layer under the nozzle
    if (step.kind === 'Print') {
      const k = clamp01(t / DUR.Print)
      const z0 = this.caseBox.min.z
      const z1 = this.caseBox.max.z
      this.clip.constant = z0 + (z1 - z0 + 0.5) * k
      this.nozzle.visible = k < 1
      const c = this.caseBox.getCenter(new Vector3())
      const sx = (this.caseBox.max.x - this.caseBox.min.x) / 2
      const sy = (this.caseBox.max.y - this.caseBox.min.y) / 2
      this.nozzle.position.set(c.x + sx * Math.sin(now * 6.1), c.y + sy * Math.sin(now * 1.7), this.clip.constant + 0.2)
    }
  }

  dispose() {
    const geos = new Set<{ dispose: () => void }>()
    for (const o of [this.root, this.extras, this.proxy]) {
      o.traverse((c) => {
        if (c instanceof Mesh || c instanceof LineSegments) {
          geos.add(c.geometry)
          const mats = Array.isArray(c.material) ? c.material : [c.material]
          for (const m of mats) geos.add(m)
        }
      })
    }
    for (const e of this.parts.values()) for (const m of e.model.mats) geos.add(m)
    for (const m of this.owned) geos.add(m)
    for (const g of geos) g.dispose()
  }
}

function screw(m: MeshStandardMaterial) {
  const g = new Group()
  const head = new Mesh(new CylinderGeometry(2.2, 2.2, 1.6, 20).rotateX(Math.PI / 2), m)
  head.position.z = 0.8
  const slot = new Mesh(new BoxGeometry(3.2, 0.55, 0.5), new MeshStandardMaterial({ color: '#3b3f45' }))
  slot.position.z = 1.62
  const slot2 = slot.clone()
  slot2.rotation.z = Math.PI / 2
  g.add(head, slot, slot2)
  return g
}
