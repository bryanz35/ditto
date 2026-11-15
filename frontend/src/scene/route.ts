// Jumper wire paths for the device view: over (or around) the parts between two pins, under the lid,
// and out through a cable hole, then checked against the parts and the printed solids.
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
/** How far a wire's centreline keeps from a part's box. */
const CLEAR = WIRE_R + 0.4
/** Within this far (sideways, mm) of a pin tip the wire is on its way onto the pin, so the parts at its
 * two ends are no obstacle there: a part's pins sit 1.5 mm in from its edge, often low on a tall part,
 * and the wire can come in at a steep angle. */
const OWN = 6
/** Sideways shifts tried, in order, when the straight route runs into something. */
const OFFSETS = [0, 4, -4, 8, -8, 12, -12, 16, -16, 20, -20, 24, -24]

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

export interface RouteOptions {
  /** The wire's sideways place in its bundle (mm). */
  spread: number
  /** Highest the inside run may go (under the lid). */
  ceiling: number
  hole?: Hole
  /** Shell hits inside this box are fine (the wire's own way through: a hole the manifest lacks, a
   * mounted part's spot). */
  allow?: Box3
  /** Solids the route height ignores (a mounted part sits on the shell, past the ceiling). */
  ignore?: string[]
  /** The parts at the wire's two ends (board, part): no obstacle within OWN of the pins. */
  own?: string[]
}

export interface Route {
  curve: Curve<Vector3>
  hits: string[]
}

const up = (p: Vector3, dz: number) => p.clone().setZ(p.z + dz)

/** The path from pin tip `from` (on the board) to pin tip `to`: the lowest clean candidate (going
 * round a tall part beats climbing over it), or the one that hits the fewest things. */
export function route(from: Vector3, to: Vector3, obs: Obstacles, o: RouteOptions): Route {
  const p0 = up(from, 2)
  const p4 = up(to, 2)
  const hole = o.hole
  // where the run over the parts ends: above the far pin, or just inside the cable hole
  const end = hole ? hole.at.clone().addScaledVector(hole.dir, -(hole.depth / 2 + 6)) : p4
  const side = new Vector3(-(end.y - p0.y), end.x - p0.x, 0).normalize()
  let best: (Route & { z: number }) | null = null
  for (const off of OFFSETS) {
    const shift = side.clone().multiplyScalar(o.spread + off)
    const m1 = p0.clone().add(shift)
    const m2 = end.clone().add(shift)
    const low = Math.max(p0.z, hole ? hole.at.z : p4.z) + 3
    const over = topAlong([p0, m1, m2, end], [p0, p4], obs.solids, o.ignore ?? [], o.own ?? []) + CLEAR + 0.3
    const z = Math.min(o.ceiling, Math.max(low, over))
    // a clean path no higher is already in hand: this one can't beat it
    if (best && !best.hits.length && z >= best.z) continue
    // straight up off the pin (a jumper's housing does), across, straight down onto the other pin
    const pts = [p0, p0.clone().setZ(z), m1.setZ(z), m2.setZ(z)]
    if (hole) {
      const room = hole.size / 2 - WIRE_R - 0.3
      const squeezed = Math.max(-room, Math.min(room, o.spread))
      const across = new Vector3(-hole.dir.y, hole.dir.x, 0).multiplyScalar(squeezed)
      const at = (d: number) => hole.at.clone().addScaledVector(hole.dir, d).add(across)
      const h = hole.depth / 2
      // outside: straight out of the hole, then up over whatever lies between it and the part
      const out = at(h + 3)
      const zo = Math.max(out.z, p4.z + 3, topAlong([out, p4], [p0, p4], obs.solids, [], o.own ?? []) + CLEAR + 0.3)
      pts.push(at(-h - 3), at(-h - 1), at(h + 1), out, out.clone().setZ(zo), p4.clone().setZ(zo), p4)
    } else pts.push(p4.clone().setZ(z), p4)
    const curve = rounded(pts)
    const hits = clips(curve, [p0, p4], obs, o.allow, o.own)
    if (!best || hits.length < best.hits.length || (hits.length === best.hits.length && z < best.z))
      best = { curve, hits, z }
  }
  return best as Route
}

/** The names of what `curve` runs into, sorted; [] when it's clear. The plugs (within 2 mm of `ends`,
 * sideways) are skipped, and the `own` parts near them: a wire starts on its pin on purpose. */
export function clips(curve: Curve<Vector3>, ends: Vector3[], obs: Obstacles, allow?: Box3, own: string[] = []) {
  const pts = curve.getSpacedPoints(Math.max(8, Math.ceil(curve.getLength())))
  const keep = pts.map((p) => !near(p, ends, 2))
  const hits = new Set<string>()
  const local = new Vector3()
  pts.forEach((p, i) => {
    if (!keep[i]) return
    for (const s of obs.solids) {
      if (own.includes(s.name) && near(p, ends, OWN)) continue
      local.copy(p).applyMatrix4(s.toLocal)
      if (Math.abs(local.x) < s.half.x && Math.abs(local.y) < s.half.y && Math.abs(local.z) < s.half.z)
        hits.add(s.name)
    }
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

/** The highest part top under a path (its corners, followed straight across), leaving out the `own`
 * parts near the pins: a low pin on a tall part doesn't send the wire over the part. */
function topAlong(path: Vector3[], ends: Vector3[], solids: Solid[], ignore: string[], own: string[]) {
  let top = -Infinity
  for (let i = 1; i < path.length; i++) {
    const n = Math.max(1, Math.ceil(path[i - 1].distanceTo(path[i])))
    for (let j = 0; j <= n; j++) {
      const p = path[i - 1].clone().lerp(path[i], j / n)
      for (const s of solids) {
        const b = s.aabb
        if (ignore.includes(s.name) || b.max.z <= top || (own.includes(s.name) && near(p, ends, OWN))) continue
        if (p.x > b.min.x - CLEAR && p.x < b.max.x + CLEAR && p.y > b.min.y - CLEAR && p.y < b.max.y + CLEAR)
          top = b.max.z
      }
    }
  }
  return top
}

/** Straight runs through `pts` with each corner rounded (up to 3 mm): unlike a spline through the
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
