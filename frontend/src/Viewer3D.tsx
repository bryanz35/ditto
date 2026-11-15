// The 3D view. With assembly.glb (T25) it draws the device: each part's box becomes a part model,
// wiring.json's rows become jumper wires, and the overview explodes / the build guide animates each
// step (scene/device.ts). Without it, the enclosure STLs (enclosure frame, mm, Z up: see
// backend/contracts/base.py); the lid is exported closed, so it is drawn see-through.
// A print-only project has no case: its printed parts (each in print orientation at the origin) are
// laid out side by side along x. A custom device's extra parts (an arm link, a knob) come in
// assembly.glb where they sit once assembled; without it (or from an older run whose glb lacks them)
// they sit in a row past the case's +x side, as they print.
import { Bounds, GizmoHelper, GizmoViewport, Grid, Html, OrbitControls } from '@react-three/drei'
import { Canvas, useFrame, useLoader, useThree, type ThreeEvent } from '@react-three/fiber'
import { Suspense, useEffect, useMemo, useRef, type ReactNode } from 'react'
import type { BufferGeometry, Group, PerspectiveCamera } from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { STLLoader } from 'three/addons/loaders/STLLoader.js'
import type { ProjectSpec, Wiring } from './contracts'
import { Device, type SceneStep } from './scene/device'
import type { Print } from './ui'

// Figma viewport variables (index.css has the same values for the page).
const BG = '#1e1e1e'
const GRID_MINOR = '#303030'
const GRID_MAJOR = '#3c3c3c'
const AXES: [string, string, string] = ['#f14c4c', '#73c991', '#3794ff']
const SHELL = '#4a4a50'

const PRINT_GAP_MM = 10

/** The floor: drei's grid lies in XZ, our frame is Z up. Just under `z`, so it doesn't show through a floor at z. */
const Floor = ({ z = 0 }: { z?: number }) => (
  <Grid
    position={[0, 0, z - 0.05]}
    rotation={[Math.PI / 2, 0, 0]}
    cellSize={4}
    sectionSize={20}
    cellColor={GRID_MINOR}
    sectionColor={GRID_MAJOR}
    fadeDistance={600}
    infiniteGrid
  />
)

function Part({ url, lid, x = 0 }: { url: string; lid: boolean; x?: number }) {
  const geometry = useLoader(STLLoader, url)
  return (
    <mesh geometry={geometry} position={[x, 0, 0]}>
      <meshStandardMaterial color={lid ? '#8b8b8b' : SHELL} transparent={lid} opacity={lid ? 0.3 : 1} />
    </mesh>
  )
}

/** A device's extra printed parts as they print: in a row past the case's +x side, on the case's floor. */
function Beside({ base, prints }: { base: string; prints: Print[] }) {
  const caseGeo = useLoader(STLLoader, base)
  const geos = useLoader(
    STLLoader,
    prints.map((p) => p.url),
  )
  const bbox = (g: BufferGeometry) => (g.computeBoundingBox(), g.boundingBox!)
  const box = bbox(caseGeo)
  const boxes = geos.map(bbox)
  // each part's left edge: past the case and the parts before it
  const xs = boxes.map((_, i) => boxes.slice(0, i).reduce((x, b) => x + b.max.x - b.min.x + PRINT_GAP_MM, box.max.x + PRINT_GAP_MM))
  return (
    <>
      {geos.map((g, i) => (
        <mesh
          key={prints[i].url}
          geometry={g}
          position={[xs[i] - boxes[i].min.x, (box.min.y + box.max.y - boxes[i].min.y - boxes[i].max.y) / 2, box.min.z - boxes[i].min.z]}
        >
          <meshStandardMaterial color={SHELL} />
        </mesh>
      ))}
    </>
  )
}

/** Centres the picture in the part of the view right of a card (`left` px), like the spike: the
 * card covers the left of the canvas. Off on narrow screens, where the card spans the width. */
function ViewOffset({ left, bottom }: { left: number; bottom: number }) {
  const camera = useThree((s) => s.camera) as PerspectiveCamera
  const size = useThree((s) => s.size)
  useEffect(() => {
    const wide = size.width > 760
    const [dx, dy] = [wide ? left / 2 : 0, wide ? bottom / 2 : 0]
    if (dx || dy) camera.setViewOffset(size.width, size.height, -dx, dy, size.width, size.height)
    else camera.clearViewOffset()
    camera.updateProjectionMatrix()
  }, [camera, size, left, bottom])
  return null
}

function DeviceView({
  url,
  spec,
  wiring,
  exploded,
  build,
  selected,
  onSelect,
  children,
}: {
  url: string
  spec: ProjectSpec | null
  wiring: Wiring | null
  exploded: boolean
  build: { steps: SceneStep[]; index: number } | null
  selected: { ref: string; label: string } | null
  onSelect?: (ref: string) => void
  /** Drawn beside the device and framed with it, unless assembly.glb has the extra printed parts. */
  children?: ReactNode
}) {
  const gltf = useLoader(GLTFLoader, url)
  const device = useMemo(() => new Device(gltf.scene, spec, wiring), [gltf, spec, wiring])
  useEffect(() => {
    // dev builds: window.__device in the console, to poke at the scene (parts, wires, setBuild, ...)
    if (import.meta.env.DEV) (window as unknown as { __device?: Device }).__device = device
    return () => device.dispose()
  }, [device])

  // steps are rebuilt on every render of the guide: restart the animation only when they change
  const buildKey = build ? `${build.index}:${build.steps.map((s) => `${s.kind}.${s.ref}`).join()}` : null
  useEffect(() => {
    if (build) device.setBuild(build.steps, build.index)
    else device.setOverview(exploded)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- buildKey stands for build
  }, [device, buildKey, exploded])
  useEffect(() => device.setSelected(selected?.ref ?? null), [device, selected?.ref])

  const label = useRef<Group>(null)
  useFrame((_, dt) => {
    device.update(Math.min(dt, 0.1))
    const at = selected ? device.anchorOf(selected.ref) : null
    if (label.current) {
      label.current.visible = at !== null
      if (at) label.current.position.copy(at)
    }
  })

  return (
    <>
      <Floor z={device.groundZ} />
      {/* the overview frames the exploded parts too (device.frame), the guide just the device */}
      <Bounds key={build ? 'build' : 'overview'} fit clip observe margin={build ? 1.2 : 1.05}>
        <primitive
          object={device.root}
          onClick={(e: ThreeEvent<MouseEvent>) => {
            e.stopPropagation()
            const ref = device.refOf(e.object)
            if (ref) onSelect?.(ref)
          }}
          onPointerMove={(e: ThreeEvent<PointerEvent>) => {
            e.stopPropagation()
            if (!build) device.setHoverPart(device.refOf(e.object))
          }}
          onPointerOut={() => device.setHoverPart(null)}
        />
        {!build && <primitive object={device.frame} />}
        {device.printed.size === 0 && children}
      </Bounds>
      {!build && (
        <primitive
          object={device.proxy}
          onPointerEnter={() => device.setHover(true)}
          onPointerLeave={() => device.setHover(false)}
        />
      )}
      <primitive object={device.extras} />
      {selected && (
        <group ref={label}>
          <Html center className="part-label" zIndexRange={[5, 0]}>
            {selected.label}
          </Html>
        </group>
      )}
    </>
  )
}

export default function Viewer3D({
  base,
  lid,
  prints = [],
  assembly,
  spec = null,
  wiring = null,
  exploded = false,
  build = null,
  selected = null,
  onSelect,
  leftInset = 0,
  bottomInset = 0,
}: {
  base: string | null
  lid: string | null
  /** Printed parts besides base and lid: a print-only project's parts (base null), or a device's
   * extras, drawn beside the case. */
  prints?: Print[]
  /** When set, draw the device from the assembly instead of the bare STLs. */
  assembly: string | null
  /** For the device: part ids of refs the assembly doesn't tag, and the parts outside the case. */
  spec?: ProjectSpec | null
  /** For the device: one jumper wire per row. */
  wiring?: Wiring | null
  /** Overview: hold the parts apart (hovering the device also pulls them apart). */
  exploded?: boolean
  /** Build guide: show the device as it is during steps[index] and play that step. */
  build?: { steps: SceneStep[]; index: number } | null
  /** The part to label (and outline) in the device. */
  selected?: { ref: string; label: string } | null
  /** Called with a part's ref when it is clicked in the device. */
  onSelect?: (ref: string) => void
  /** Width (px) of the card over the view's left side: the model centres in the space right of it. */
  leftInset?: number
  /** Height (px) of what covers the view's bottom (the overview's dock): the model centres above it. */
  bottomInset?: number
}) {
  // each part's centre: past the ones before it, plus half its own width
  const xs = prints.map((_, i) => prints.slice(0, i).reduce((x, p) => x + p.width + PRINT_GAP_MM, prints[i].width / 2))
  const beside = base && prints.length > 0 ? <Beside base={base} prints={prints} /> : null
  return (
    <Canvas
      camera={{ position: [120, -160, 140], up: [0, 0, 1], far: 5000 }}
      onCreated={({ gl }) => {
        // the print step grows the case with a clipping plane
        gl.localClippingEnabled = true
      }}
    >
      <color attach="background" args={[BG]} />
      <ambientLight intensity={0.7} />
      <directionalLight position={[100, -100, 200]} intensity={1.5} />
      <directionalLight position={[-120, 90, 80]} intensity={0.5} />
      {!assembly && <Floor />}
      <ViewOffset left={leftInset} bottom={bottomInset} />
      <Suspense fallback={null}>
        {assembly ? (
          <DeviceView
            url={assembly}
            spec={spec}
            wiring={wiring}
            exploded={exploded}
            build={build}
            selected={selected}
            onSelect={onSelect}
          >
            {beside}
          </DeviceView>
        ) : (
          <Bounds key="enclosure" fit clip observe margin={1.3}>
            {base && <Part url={base} lid={false} />}
            {lid && <Part url={lid} lid />}
            {base
              ? beside
              : prints.map((p, i) => <Part key={p.url} url={p.url} lid={false} x={xs[i]} />)}
          </Bounds>
        )}
      </Suspense>
      <OrbitControls makeDefault />
      <GizmoHelper alignment="bottom-right" margin={[56, 56]}>
        <GizmoViewport axisColors={AXES} labelColor={BG} />
      </GizmoHelper>
    </Canvas>
  )
}
