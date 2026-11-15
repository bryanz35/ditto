// Jumper wire paths for the device view: the shortest way between two pins that misses the parts, the
// printed solids and the wires already laid, under the lid, and out through a cable hole.
// Frame: the enclosure's (mm, Z up), like device.ts.
import {
  Box3,
  CurvePath,
  DoubleSide,
  LineCurve3,
  Matrix4,
  QuadraticBezierCurve3,
  Quaternion,
  Ray,
  Vector3,
  type Curve,
  type Mesh,
} from 'three'
import { MeshBVH } from 'three-mesh-bvh'

export const WIRE_R = 0.6
/** How far a wire's centreline keeps from a part's box or a printed surface. */
const CLEAR = WIRE_R + 0.4
/** Within this far (sideways, mm) of a pin tip, and no lower than it, the wire is on its way onto the
 * pin, so the parts at its two ends are no obstacle there: a part's pins sit 1.5 mm in from its edge,
 * often low on a tall part, and the wire can come in at a steep angle. */
const OWN = 6
/** Extra room the search keeps from a part's box, so rounding a corner doesn't cut into it. */
const GAP = 0.5
/** Search grid spacing (mm). At most 2 * CLEAR, so every surface blocks a full layer of cells. */
const PITCH = 1.5
/** How far apart two wires' centrelines are kept while routing (the final check allows 2 * WIRE_R). */
const SEP = 2 * WIRE_R + 0.3
/** Sample spacing along a wire (mm), for the wire field and the shortcut checks. */
const STEP = 0.5
/** How far the search may stray sideways from a leg's two ends (mm). */
const MARGIN = 25
/** What running next to another wire costs, per grid cell, in mm of extra length: wires cross only
 * where a clear way would be far longer. */
const CROSS = 30
/** Cells the search may expand before a leg gives up. */
const MAX_CELLS = 12000
/** Wires through the same cable hole bunch up within this far of it, so they may touch there; so do
 * wires on one pin, within SHARED of its plug's top. */
const HOLE_ZONE = 8
const SHARED = 6

/** A part's layout box, where it sits and how it's turned. */
export interface Solid {
  name: string
  toLocal: Matrix4
  half: Vector3
  aabb: Box3
}

export function solid(name: string, center: Vector3, turn: Quaternion, size: Vector3): Solid {
  const m = new Matrix4().compose(center, turn, new Vector3(1, 1, 1))
  return {
    name,
    toLocal: m.clone().invert(),
    half: size.clone().multiplyScalar(0.5).addScalar(CLEAR),
    aabb: new Box3().setFromCenterAndSize(new Vector3(), size).applyMatrix4(m),
  }
}

/** A printed part (case, lid, a custom device's prints): hollow, so wires are checked against its
 * triangles (through a BVH: custom bodies run to tens of thousands). */
export interface Shell {
  name: string
  bvh: MeshBVH
  toLocal: Matrix4
  toWorld: Matrix4
}

/** `mesh` as a shell, where it sits now; its name is what a hit reports. */
export function shell(mesh: Mesh): Shell {
  mesh.updateWorldMatrix(true, false)
  return {
    name: mesh.name,
    bvh: new MeshBVH(mesh.geometry, { indirect: true }), // indirect: leaves the drawn geometry as it is
    toLocal: mesh.matrixWorld.clone().invert(),
    toWorld: mesh.matrixWorld.clone(),
  }
}

/** What wires must miss. */
export interface Obstacles {
  solids: Solid[]
  shells: Shell[]
}

/** A cable hole a wire leaves the case through: its centre, the way out, and the wall it's in. */
export interface Hole {
  at: Vector3
  dir: Vector3
  depth: number
  /** Hole width: the wires bunch up to fit it. */
  size: number
}

/** The wires laid so far (centreline samples, hashed by grid cell): later wires keep off them. One per
 * device, shared by its wires. */
export interface Field {
  cells: Map<number, { p: Vector3; id: string }[]>
  /** How many wires each pin tip has (`reserve`): wires on one pin (a shared 3V3, an I2C bus) touch there. */
  pins: Map<string, number>
}

export const field = (): Field => ({ cells: new Map(), pins: new Map() })
const pinKey = (p: Vector3) => p.toArray().map((v) => v.toFixed(2)).join()

export interface RouteOptions {
  /** The wire's sideways place in its cable hole (mm). */
  spread: number
  /** Highest the inside run may go (under the lid). */
  ceiling: number
  /** Lowest a run may go (the case floor); without it, no lower than its two ends. */
  floor?: number
  hole?: Hole
  /** Shell hits inside this box are fine, and so is going above the ceiling (the wire's own way through:
   * a hole the manifest lacks, a mounted part's spot). */
  allow?: Box3
  /** The parts at the wire's two ends (board, part): no obstacle within OWN of the pins. */
  own?: string[]
  /** The wires already laid (and the pins reserved): this one keeps off them, then joins them. */
  field?: Field
  /** This wire's name in the field, and in other wires' hits as `wire:<id>`. */
  id?: string
}

export interface Route {
  curve: Curve<Vector3>
  hits: string[]
}

const up = (p: Vector3, dz: number) => p.clone().setZ(p.z + dz)
/** Where a wire's straight rise off pin tip `p` ends: 5 mm up (the 2 mm housing, then the bend), kept
 * under `ceiling` when there's room. */
const lift = (p: Vector3, ceiling: number) => up(p, Math.max(2, Math.min(5, ceiling - p.z)))

/** Claims the straight rises off a wire's two pins before any wire is routed, so the wires laid first
 * keep off the pins of the ones laid later. */
export function reserve(f: Field, id: string, from: Vector3, to: Vector3, o: RouteOptions) {
  for (const p of [from, to]) f.pins.set(pinKey(p), (f.pins.get(pinKey(p)) ?? 0) + 1)
  claim(f, id, [from, lift(from, o.ceiling)])
  claim(f, id, [to, lift(to, o.hole ? Infinity : o.ceiling)])
}

/** The path from pin tip `from` (on the board) to pin tip `to`: straight up off the pin (a jumper's
 * housing does), the shortest clear way across (grid search, then straightened), straight down onto the
 * other pin. An outside part's wire goes through its cable hole between two such legs. The wire then
 * joins `o.field`. */
export function route(from: Vector3, to: Vector3, obs: Obstacles, o: RouteOptions): Route {
  const id = o.id ?? 'wire'
  const f = o.field ?? field()
  const p0 = up(from, 2)
  const p4 = up(to, 2)
  const hole = o.hole
  const shared = [from, to].filter((p) => (f.pins.get(pinKey(p)) ?? 0) > 1).map((p) => up(p, 2))
  const ctx: Leg = {
    obs,
    ends: [p0, p4],
    own: o.own ?? [],
    allow: o.allow,
    f,
    id,
    floor: o.floor,
    zone: (p) => (!!hole && p.distanceTo(hole.at) < HOLE_ZONE) || shared.some((e) => p.distanceTo(e) < SHARED),
  }
  let pts: Vector3[]
  if (hole) {
    const room = hole.size / 2 - WIRE_R - 0.3
    const squeezed = Math.max(-room, Math.min(room, o.spread))
    const across = new Vector3(-hole.dir.y, hole.dir.x, 0).multiplyScalar(squeezed)
    const at = (d: number) => hole.at.clone().addScaledVector(hole.dir, d).add(across)
    const h = hole.depth / 2
    // inside to just short of the hole, straight through it, then outside on to the part
    const inside = leg(ctx, lift(from, o.ceiling), at(-h - 5), o.ceiling)
    const outside = leg(ctx, at(h + 5), lift(to, Infinity), Infinity)
    pts = [p0, ...inside, at(-h - 1), at(h + 1), ...outside, p4]
  } else pts = [p0, ...leg(ctx, lift(from, o.ceiling), lift(to, o.ceiling), o.ceiling), p4]
  let curve = rounded(pts)
  let hits = report(ctx, curve)
  if (hits.length) {
    // a 3 mm corner can cut into what the straight runs just miss
    const tight = rounded(pts, 1)
    const h = report(ctx, tight)
    if (h.length < hits.length) [curve, hits] = [tight, h]
  }
  claim(f, id, curve.getSpacedPoints(Math.ceil(curve.getLength() / STEP)))
  return { curve, hits }
}

/** The names of what `curve` runs into, sorted; [] when it's clear. The plugs (within 2 mm of `ends`,
 * sideways) are skipped, and the `own` parts near them: a wire starts on its pin on purpose. */
export function clips(curve: Curve<Vector3>, ends: Vector3[], obs: Obstacles, allow?: Box3, own: string[] = []) {
  const pts = curve.getSpacedPoints(Math.max(8, Math.ceil(curve.getLength())))
  const keep = pts.map((p) => !near(p, ends, 2))
  const hits = new Set<string>()
  pts.forEach((p, i) => {
    if (!keep[i]) return
    for (const s of obs.solids) if (!(own.includes(s.name) && onto(p, ends)) && inside(s, p)) hits.add(s.name)
  })
  // shortcut: shells are checked along the centreline only, so a graze under the 0.6 mm wire radius
  // can still show; cast a ring of rays per step if that turns up
  const ray = new Ray()
  const a = new Vector3()
  const b = new Vector3()
  for (const sh of obs.shells) {
    for (let i = 1; i < pts.length && !hits.has(sh.name); i++) {
      if (!keep[i - 1] || !keep[i]) continue
      a.copy(pts[i - 1]).applyMatrix4(sh.toLocal)
      b.copy(pts[i]).applyMatrix4(sh.toLocal)
      const len = a.distanceTo(b)
      ray.set(a, b.sub(a).normalize())
      const crossed = sh.bvh.raycast(ray, DoubleSide, 0, len)
      if (crossed.some((h) => !allow?.containsPoint(h.point.applyMatrix4(sh.toWorld)))) hits.add(sh.name)
    }
  }
  return [...hits].sort()
}

const near = (p: Vector3, ends: Vector3[], r: number) => ends.some((e) => Math.hypot(p.x - e.x, p.y - e.y) <= r)
/** Whether `p` is on the way onto a pin (`ends` are the plugs' tops, 2 mm over the tips): see OWN. */
const onto = (p: Vector3, ends: Vector3[]) =>
  ends.some((e) => Math.hypot(p.x - e.x, p.y - e.y) <= OWN && p.z >= e.z - 2)

const local = new Vector3()
/** Whether `p` is inside part `s`'s box grown by CLEAR + `gap`. */
const inside = (s: Solid, p: Vector3, gap = 0) => {
  local.copy(p).applyMatrix4(s.toLocal)
  return Math.abs(local.x) < s.half.x + gap && Math.abs(local.y) < s.half.y + gap && Math.abs(local.z) < s.half.z + gap
}

/** One wire's routing context. */
interface Leg {
  obs: Obstacles
  /** The plugs' tops (pin tip + 2). */
  ends: Vector3[]
  own: string[]
  allow?: Box3
  f: Field
  id: string
  floor?: number
  /** Where the field doesn't count (the wire's cable hole, a pin it shares). */
  zone: (p: Vector3) => boolean
}

/** What `curve` hits: parts and shells (`clips`), and other wires closer than touching (`wire:<id>`),
 * outside the hole zone. */
function report(c: Leg, curve: Curve<Vector3>) {
  const hits = new Set(clips(curve, c.ends, c.obs, c.allow, c.own))
  const wires = new Set<string>()
  for (const p of curve.getSpacedPoints(Math.ceil(curve.getLength() / STEP)))
    if (!c.zone(p)) crowd(c.f, p, c.id, 2 * WIRE_R, wires)
  for (const w of wires) hits.add(`wire:${w}`)
  return [...hits].sort()
}

/** Waypoints from `a` to `b` (both included) under `ceiling`: the shortest grid path, straightened, or
 * the old plain way up to the ceiling and across when the parts leave none. */
function leg(c: Leg, a: Vector3, b: Vector3, ceiling: number): Vector3[] {
  const path = search(c, a, b, ceiling)
  if (path) return straighten(c, path, ceiling)
  const z = Number.isFinite(ceiling) ? Math.max(ceiling, a.z, b.z) : Math.max(a.z, b.z) + 10
  return [a, a.clone().setZ(z), b.clone().setZ(z), b]
}

// grid cells: integer coordinates packed into 30 bits, so Map keys stay small integers (fast)
// shortcut: ±512 cells a side (±768 mm) wraps beyond that; widen the packing if a device ever gets that big
const pack = (i: number, j: number, k: number) => (((i + 512) & 1023) << 20) | (((j + 512) & 1023) << 10) | ((k + 512) & 1023)
const unpack = (key: number): [number, number, number] => [(key >> 20) - 512, ((key >> 10) & 1023) - 512, (key & 1023) - 512]
const DIRS = [
  [1, 0, 0],
  [-1, 0, 0],
  [0, 1, 0],
  [0, -1, 0],
  [0, 0, 1],
  [0, 0, -1],
]

/** What blocks each grid cell, per obstacle set: the parts' names, and whether a shell is within CLEAR.
 * Shared by all the wires of a device. */
const cellMemo = new WeakMap<Obstacles, Map<number, { solids: string[]; shell: boolean }>>()

function obstaclesAt(obs: Obstacles, key: number, c: Vector3) {
  let memo = cellMemo.get(obs)
  if (!memo) cellMemo.set(obs, (memo = new Map()))
  let m = memo.get(key)
  if (m) return m
  const solids = obs.solids.filter((s) => inside(s, c, GAP)).map((s) => s.name)
  const at = new Vector3()
  const shell = obs.shells.some((sh) => {
    const hit = sh.bvh.closestPointToPoint(at.copy(c).applyMatrix4(sh.toLocal), undefined, CLEAR, CLEAR)
    return !!hit && hit.distance < CLEAR
  })
  memo.set(key, (m = { solids, shell }))
  return m
}

/** A* over the grid from `a`'s cell to `b`'s (6 neighbours, cost = length, plus CROSS for each cell
 * another wire is too close to): the cells' centres between the two points, with `a` and `b` themselves
 * at the ends, or null when the parts and shells leave no way. */
function search(c: Leg, a: Vector3, b: Vector3, ceiling: number): Vector3[] | null {
  const cell = (p: Vector3) => [Math.round(p.x / PITCH), Math.round(p.y / PITCH), Math.round(p.z / PITCH)]
  const [ai, aj, ak] = cell(a)
  const [bi, bj, bk] = cell(b)
  const start = pack(ai, aj, ak)
  const goal = pack(bi, bj, bk)
  const lo = [Math.min(a.x, b.x) - MARGIN, Math.min(a.y, b.y) - MARGIN, c.floor ?? Math.min(a.z, b.z)]
  const top = Number.isFinite(ceiling) ? Math.max(ceiling, a.z, b.z) : Math.max(a.z, b.z) + 30
  const hi = [Math.max(a.x, b.x) + MARGIN, Math.max(a.y, b.y) + MARGIN, top]
  const min = lo.map((v) => Math.floor(v / PITCH))
  const max = hi.map((v) => Math.floor(v / PITCH))
  const centre = new Vector3()
  const costs = new Map<number, number>()
  /** What stepping into a cell costs: Infinity when it's blocked. */
  const cost = (i: number, j: number, k: number, key: number) => {
    let w = costs.get(key)
    if (w !== undefined) return w
    const p = centre.set(i * PITCH, j * PITCH, k * PITCH)
    const allowed = !!c.allow?.containsPoint(p)
    const o = obstaclesAt(c.obs, key, p)
    const open =
      (p.z <= ceiling || allowed) && (!o.shell || allowed) && o.solids.every((n) => c.own.includes(n) && onto(p, c.ends))
    w = !open ? Infinity : PITCH + (crowded(c, p) ? CROSS : 0)
    costs.set(key, w)
    return w
  }
  // weighted (greedy-leaning) for speed: the straightening takes out most of what that costs in length
  const h = (i: number, j: number, k: number) => Math.hypot(i - bi, j - bj, k - bk) * PITCH * 1.3
  const g = new Map([[start, 0]])
  const parent = new Map<number, number>()
  const open = new Heap()
  open.push([h(ai, aj, ak), h(ai, aj, ak), start])
  const done = new Set<number>()
  while (open.size && done.size < MAX_CELLS) {
    const [, , key] = open.pop()
    if (key === goal) {
      const cells: number[] = []
      for (let k: number | undefined = parent.get(goal); k !== undefined && k !== start; k = parent.get(k))
        cells.unshift(k)
      return [a, ...cells.map((k) => new Vector3(...unpack(k)).multiplyScalar(PITCH)), b]
    }
    if (done.has(key)) continue
    done.add(key)
    const [i, j, k] = unpack(key)
    const gk = g.get(key)!
    for (const [di, dj, dk] of DIRS) {
      const [ni, nj, nk] = [i + di, j + dj, k + dk]
      if (ni < min[0] || nj < min[1] || nk < min[2] || ni > max[0] || nj > max[1] || nk > max[2]) continue
      const nkey = pack(ni, nj, nk)
      if (done.has(nkey)) continue
      const ng = gk + (nkey === goal ? PITCH : cost(ni, nj, nk, nkey))
      if (ng === Infinity || ng >= (g.get(nkey) ?? Infinity)) continue
      g.set(nkey, ng)
      parent.set(nkey, key)
      const hn = h(ni, nj, nk)
      open.push([ng + hn, hn, nkey])
    }
  }
  return null
}

/** Drops each waypoint the straight run past it doesn't need (string pulling): the grid's staircase
 * becomes straight runs at any angle. A shortcut must miss the parts and shells, and run no nearer the
 * other wires than the way it replaces (where the search had to cross one, the shortcut may too). */
function straighten(c: Leg, path: Vector3[], ceiling: number): Vector3[] {
  const p = new Vector3()
  const samples = (a: Vector3, b: Vector3) => Math.max(1, Math.ceil(a.distanceTo(b) / STEP))
  /** Samples of a→b too near another wire, or -1 when a→b is blocked. */
  const close = (a: Vector3, b: Vector3) => {
    const n = samples(a, b)
    let near = 0
    for (let t = 0; t <= n; t++) {
      p.copy(a).lerp(b, t / n)
      if (p.z > ceiling + 1e-6 && !c.allow?.containsPoint(p)) return -1
      if (!onEnd(p, c.ends) && c.obs.solids.some((s) => inside(s, p, GAP) && !(c.own.includes(s.name) && onto(p, c.ends))))
        return -1
      if (crowded(c, p)) near++
    }
    return clips(new LineCurve3(a, b), c.ends, c.obs, c.allow, c.own).length ? -1 : near
  }
  // how near the other wires the grid path runs, up to each waypoint (its steps are clear of the rest)
  const sum = [0]
  for (let k = 1; k < path.length; k++) {
    let near = 0
    for (let t = 0, n = samples(path[k - 1], path[k]); t < n; t++)
      if (crowded(c, p.copy(path[k - 1]).lerp(path[k], t / n))) near++
    sum.push(sum[k - 1] + near)
  }
  const ok = (i: number, j: number) => {
    const n = close(path[i], path[j])
    return n >= 0 && n <= sum[j] - sum[i]
  }
  const out = [path[0]]
  const last = path.length - 1
  for (let i = 0; i < last; ) {
    // the farthest waypoint in sight: gallop out, then halve back (sight isn't monotonic, so this
    // can miss one; the path is still clear)
    let j = i + 1
    if (ok(i, last)) j = last
    else {
      let step = 1
      while (j + step < last && ok(i, j + step)) j += (step *= 2) / 2
      for (step = Math.floor(step / 2); step >= 1; step = Math.floor(step / 2)) if (j + step < last && ok(i, j + step)) j += step
    }
    out.push(path[j])
    i = j
  }
  return out
}

/** Whether another wire is within SEP of `p` (outside the wire's cable hole, where they bunch up). */
const crowded = (c: Leg, p: Vector3) => !c.zone(p) && crowd(c.f, p, c.id, SEP)
const onEnd = (p: Vector3, ends: Vector3[]) => near(p, ends, 2)

const fkey = (x: number, y: number, z: number) =>
  pack(Math.floor(x / PITCH), Math.floor(y / PITCH), Math.floor(z / PITCH))

/** Adds the polyline `pts` to the field as wire `id`, a sample every STEP mm. */
function claim(f: Field, id: string, pts: Vector3[]) {
  for (let i = 1; i < pts.length; i++) {
    const n = Math.max(1, Math.ceil(pts[i - 1].distanceTo(pts[i]) / STEP))
    for (let t = i === 1 ? 0 : 1; t <= n; t++) {
      const p = pts[i - 1].clone().lerp(pts[i], t / n)
      const key = fkey(p.x, p.y, p.z)
      const list = f.cells.get(key)
      if (list) list.push({ p, id })
      else f.cells.set(key, [{ p, id }])
    }
  }
}

/** Whether another wire passes within `r` (<= PITCH) of `p`; with `into`, every such wire is added
 * there instead of stopping at the first. */
function crowd(f: Field, p: Vector3, id: string, r: number, into?: Set<string>): boolean {
  const [i, j, k] = [Math.floor(p.x / PITCH), Math.floor(p.y / PITCH), Math.floor(p.z / PITCH)]
  const r2 = r * r
  for (let di = -1; di <= 1; di++)
    for (let dj = -1; dj <= 1; dj++)
      for (let dk = -1; dk <= 1; dk++)
        for (const s of f.cells.get(pack(i + di, j + dj, k + dk)) ?? [])
          if (s.id !== id && s.p.distanceToSquared(p) < r2) {
            if (!into) return true
            into.add(s.id)
          }
  return !!into?.size
}

/** A binary min-heap of [f, h, key], ties going to the lower h (nearer the goal). */
class Heap {
  private a: [number, number, number][] = []
  get size() {
    return this.a.length
  }
  push(e: [number, number, number]) {
    const a = this.a
    a.push(e)
    for (let i = a.length - 1; i > 0; ) {
      const p = (i - 1) >> 1
      if (!less(a[i], a[p])) break
      ;[a[i], a[p]] = [a[p], a[i]]
      i = p
    }
  }
  pop() {
    const a = this.a
    const top = a[0]
    const last = a.pop()!
    if (a.length) {
      a[0] = last
      for (let i = 0; ; ) {
        const l = 2 * i + 1
        let m = i
        if (l < a.length && less(a[l], a[m])) m = l
        if (l + 1 < a.length && less(a[l + 1], a[m])) m = l + 1
        if (m === i) break
        ;[a[i], a[m]] = [a[m], a[i]]
        i = m
      }
    }
    return top
  }
}

const less = (x: [number, number, number], y: [number, number, number]) =>
  x[0] < y[0] - 1e-9 || (x[0] <= y[0] + 1e-9 && x[1] < y[1])

/** Straight runs through `pts` with each corner rounded (up to `r` mm): unlike a spline through the
 * corners it never bulges past them, so a run at the ceiling stays under it. */
export function rounded(points: Vector3[], r = 3): CurvePath<Vector3> {
  const pts = points.filter((p, i) => i === 0 || p.distanceTo(points[i - 1]) > 0.01)
  const path = new CurvePath<Vector3>()
  const line = (a: Vector3, b: Vector3) => a.distanceTo(b) > 1e-6 && path.add(new LineCurve3(a, b))
  let start = pts[0]
  for (let i = 1; i < pts.length - 1; i++) {
    const [a, b, c] = [pts[i - 1], pts[i], pts[i + 1]]
    const p = b.clone().lerp(a, Math.min(0.5, r / a.distanceTo(b)))
    const q = b.clone().lerp(c, Math.min(0.5, r / b.distanceTo(c)))
    line(start, p)
    path.add(new QuadraticBezierCurve3(p, b, q))
    start = q
  }
  line(start, pts[pts.length - 1])
  return path
}
