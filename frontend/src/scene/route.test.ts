import { BoxGeometry, CatmullRomCurve3, DoubleSide, Mesh, MeshBasicMaterial, Quaternion, Vector3, type Curve } from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { describe, expect, it } from 'vitest'
import glbData from '../../../fixtures/runs/plant_monitor/cad/assembly.glb?inline'
import manifestJson from '../../../fixtures/runs/plant_monitor/cad/manifest.json'
import specJson from '../../../fixtures/runs/plant_monitor/spec.json'
import wiringJson from '../../../fixtures/runs/plant_monitor/wiring.json'
import type { EnclosureManifest, ProjectSpec, Wiring } from '../contracts'
import { Device } from './device'
import { clips, field, reserve, route, shell, solid, WIRE_R, type Obstacles, type RouteOptions } from './route'

const v = (x: number, y: number, z: number) => new Vector3(x, y, z)
const part = (name: string, c: Vector3, size: Vector3) => solid(name, c, new Quaternion(), size)
const slab = (name: string, c: Vector3, size: Vector3) => {
  const m = new Mesh(new BoxGeometry(size.x, size.y, size.z), new MeshBasicMaterial({ side: DoubleSide }))
  m.name = name
  m.position.copy(c)
  return shell(m)
}
const maxZ = (c: Curve<Vector3>) => Math.max(...c.getSpacedPoints(200).map((p) => p.z))
const from = v(0, 0, 10)
const to = v(60, 0, 10)
const straight = new CatmullRomCurve3([v(0, 0, 12), v(30, 0, 12), v(60, 0, 12)])
const none: Obstacles = { solids: [], shells: [] }
/** The closest two curves come (sampled every 0.25 mm). */
const gap = (a: Curve<Vector3>, b: Curve<Vector3>) => {
  const pb = b.getSpacedPoints(Math.ceil(b.getLength() * 4))
  let min = Infinity
  for (const p of a.getSpacedPoints(Math.ceil(a.getLength() * 4))) for (const q of pb) min = Math.min(min, p.distanceTo(q))
  return min
}
/** Routes wires the way device.ts does: every pin reserved, then each wire in turn on one field. */
const routeAll = (ends: Vector3[][], o: Omit<RouteOptions, 'field' | 'id'>) => {
  const f = field()
  const opts = ends.map((_, i) => ({ ...o, field: f, id: `w${i}` }))
  ends.forEach(([a, b], i) => reserve(f, `w${i}`, a, b, opts[i]))
  return ends.map(([a, b], i) => route(a, b, none, opts[i]))
}

describe('route', () => {
  it('goes over a taller part it cannot go round', () => {
    const obs: Obstacles = { solids: [part('tall', v(30, 0, 7), v(10, 80, 14))], shells: [] }
    expect(clips(straight, [from, to], obs)).toEqual(['tall'])
    const r = route(from, to, obs, { spread: 0, ceiling: 30 })
    expect(r.hits).toEqual([])
    expect(maxZ(r.curve)).toBeGreaterThan(14.6)
  })

  it('goes round a tall part rather than climbing over it', () => {
    const obs: Obstacles = { solids: [part('tower', v(30, 0, 20), v(10, 10, 40))], shells: [] }
    const r = route(from, to, obs, { spread: 0, ceiling: 60 })
    expect(r.hits).toEqual([])
    expect(maxZ(r.curve)).toBeLessThan(15.01) // just over the pin tips (12 + 3), not over the 40 mm tower
  })

  it('stays low to a low pin on a tall part, even coming in at an angle', () => {
    // a 40 mm tall button with its pins 1.5 mm in from the edge facing the board, 10 mm up
    const obs: Obstacles = { solids: [part('button', v(40, 0, 20), v(20, 20, 40))], shells: [] }
    for (const start of [from, v(10, 25, 10)]) {
      const r = route(start, v(31.5, 0, 10), obs, { spread: 0, ceiling: 60, own: ['button'] })
      expect(r.hits).toEqual([])
      expect(maxZ(r.curve)).toBeLessThan(15.01)
    }
  })

  it('still keeps clear of other parts near a pin', () => {
    // a tall neighbour 2 mm from the pin, across the way in: the wire goes over or round it, not through
    const cap = part('cap', v(27, 0, 15), v(3, 6, 30))
    const obs: Obstacles = { solids: [part('button', v(40, 0, 20), v(20, 20, 40)), cap], shells: [] }
    const pin = v(31.5, 0, 10)
    const r = route(from, pin, obs, { spread: 0, ceiling: 60, own: ['button'] })
    expect(r.hits).toEqual([])
    expect(clips(r.curve, [from, pin].map((p) => p.clone().setZ(12)), { solids: [cap], shells: [] })).toEqual([])
  })

  it('goes round a part that reaches the lid', () => {
    const obs: Obstacles = { solids: [part('tall', v(30, 0, 12), v(10, 10, 24))], shells: [] }
    const r = route(from, to, obs, { spread: 0, ceiling: 18 })
    expect(r.hits).toEqual([])
    expect(maxZ(r.curve)).toBeLessThanOrEqual(18.01)
  })

  it('reports a printed post in the way and goes round it', () => {
    const obs: Obstacles = { solids: [], shells: [slab('post', v(30, 0, 10), v(6, 6, 40))] }
    expect(clips(straight, [from, to], obs)).toEqual(['post'])
    expect(route(from, to, obs, { spread: 0, ceiling: 18 }).hits).toEqual([])
  })

  it('leaves the case through the cable hole', () => {
    // back wall at y 39..41 with a 6 mm hole centred at x 30, z 8
    const wall = [
      slab('base', v(3.5, 40, 14), v(47, 2, 32)),
      slab('base', v(56.5, 40, 14), v(47, 2, 32)),
      slab('base', v(30, 40, 1.5), v(6, 2, 7)),
      slab('base', v(30, 40, 20.5), v(6, 2, 19)),
    ]
    const obs: Obstacles = { solids: [], shells: wall }
    const hole = { at: v(30, 40, 8), dir: v(0, 1, 0), depth: 2, size: 6 }
    for (const spread of [-2.4, 0, 2.4]) {
      const r = route(v(10, 10, 10), v(30, 60, 6), obs, { spread, ceiling: 18, hole })
      expect(r.hits).toEqual([])
      const inWall = r.curve.getSpacedPoints(400).filter((p) => Math.abs(p.y - 40) < 1)
      expect(inWall.length).toBeGreaterThan(0)
      for (const p of inWall) expect(Math.hypot(p.x - 30, p.z - 8)).toBeLessThan(3 - 0.6)
    }
  })
})

describe('wires together', () => {
  it('takes the straight way when nothing is in it', () => {
    const end = v(40, 30, 10)
    const r = route(from, end, none, { spread: 0, ceiling: 30 })
    expect(r.hits).toEqual([])
    expect(r.curve.getLength()).toBeLessThan(from.distanceTo(end) * 1.1 + 6) // 6: the rises off the pins
  })

  it('hops a part a little taller than the pins rather than going far round it', () => {
    const obs: Obstacles = { solids: [part('bump', v(30, 0, 8), v(10, 30, 16))], shells: [] }
    const r = route(from, to, obs, { spread: 0, ceiling: 30 })
    expect(r.hits).toEqual([])
    expect(r.curve.getLength()).toBeLessThan(60 * 1.1 + 6)
  })

  it('keeps two crossing wires apart', () => {
    const [a, b] = routeAll(
      [
        [v(0, 0, 10), v(40, 40, 10)],
        [v(0, 40, 10), v(40, 0, 10)],
      ],
      { spread: 0, ceiling: 30 },
    )
    expect([a.hits, b.hits]).toEqual([[], []])
    expect(gap(a.curve, b.curve)).toBeGreaterThanOrEqual(2 * WIRE_R)
  })

  it('keeps four header wires apart when they swap order', () => {
    const rs = routeAll(
      [0, 1, 2, 3].map((k) => [v(0, 2.54 * k, 10), v(40, 2.54 * (3 - k), 10)]),
      { spread: 0, ceiling: 30 },
    )
    for (const r of rs) expect(r.hits).toEqual([])
    for (let i = 0; i < 4; i++)
      for (let j = i + 1; j < 4; j++) expect(gap(rs[i].curve, rs[j].curve)).toBeGreaterThanOrEqual(2 * WIRE_R)
  })
})

describe('the plant_monitor device', () => {
  it('routes every inside wire clear of the case, the parts and each other', async () => {
    const bin = atob(glbData.slice(glbData.indexOf(',') + 1))
    const buf = Uint8Array.from(bin, (c) => c.charCodeAt(0)).buffer
    const gltf = await new GLTFLoader().parseAsync(buf, '')
    const wiring = wiringJson as Wiring
    const device = new Device(gltf.scene, specJson as unknown as ProjectSpec, wiring, manifestJson as EnclosureManifest)
    // the fixture's base.stl is a plain open box, without the cutouts, so soil1's wires (outside the
    // case) can only cross its back wall where the cable hole should be
    const want = wiring.rows.map((r) => [`${r.part_ref}.${r.part_pin}`, r.part_ref === 'soil1' ? ['base'] : []])
    expect(device.wireClips()).toEqual(Object.fromEntries(want))
    device.dispose()
  })
})
