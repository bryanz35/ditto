// The enclosure STLs (enclosure frame, mm, Z up: see backend/contracts/base.py). The lid is
// exported in its closed position, so it is drawn see-through to show the base inside.
// assembly.glb (T25) is in the same frame, with the lid raised and every part placed; its part nodes
// are named by ref and carry the part_id in their extras (backend/cad/assembly.py).
import { Bounds, GizmoHelper, GizmoViewport, Grid, Html, OrbitControls } from '@react-three/drei'
import { Canvas, useLoader, type ThreeEvent } from '@react-three/fiber'
import { Suspense, useEffect, useMemo } from 'react'
import { Box3, Mesh, MeshStandardMaterial, Vector3 } from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { STLLoader } from 'three/addons/loaders/STLLoader.js'

// Figma viewport variables (index.css has the same values for the page).
const BG = '#1e1e1e'
const GRID_MINOR = '#303030'
const GRID_MAJOR = '#3c3c3c'
const AXES: [string, string, string] = ['#f14c4c', '#73c991', '#3794ff']
const SHELL = '#4a4a50'

function Part({ url, lid }: { url: string; lid: boolean }) {
  const geometry = useLoader(STLLoader, url)
  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial color={lid ? '#8b8b8b' : SHELL} transparent={lid} opacity={lid ? 0.3 : 1} />
    </mesh>
  )
}

function Assembly({
  url,
  selected,
  onSelect,
}: {
  url: string
  selected: { ref: string; label: string } | null
  onSelect?: (ref: string) => void
}) {
  const gltf = useLoader(GLTFLoader, url)
  // the GLB paints base and lid light grey; the design's case is dark (parts keep their category colours)
  useEffect(() => {
    gltf.scene.traverse((o) => {
      if (o instanceof Mesh && !o.userData.part_id) o.material = new MeshStandardMaterial({ color: SHELL })
    })
  }, [gltf])
  // the label sits on top of the selected part
  const anchor = useMemo(() => {
    const node = selected && gltf.scene.getObjectByName(selected.ref)
    if (!node) return null
    const box = new Box3().setFromObject(node)
    return box.getCenter(new Vector3()).setZ(box.max.z)
  }, [gltf, selected])
  return (
    <>
      <primitive
        object={gltf.scene}
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation()
          if (e.object.userData.part_id) onSelect?.(e.object.name)
        }}
      />
      {anchor && selected && (
        <Html position={anchor} center className="part-label" zIndexRange={[5, 0]}>
          {selected.label}
        </Html>
      )}
    </>
  )
}

export default function Viewer3D({
  base,
  lid,
  assembly,
  selected = null,
  onSelect,
}: {
  base: string | null
  lid: string | null
  /** When set, show the assembly instead of the STLs. */
  assembly: string | null
  /** The part to label in the assembly. */
  selected?: { ref: string; label: string } | null
  /** Called with a part's ref when it is clicked in the assembly. */
  onSelect?: (ref: string) => void
}) {
  return (
    <Canvas camera={{ position: [120, -160, 140], up: [0, 0, 1], far: 5000 }}>
      <color attach="background" args={[BG]} />
      <ambientLight intensity={0.7} />
      <directionalLight position={[100, -100, 200]} intensity={1.5} />
      {/* the floor: drei's grid lies in XZ, our frame is Z up */}
      <Grid
        rotation={[Math.PI / 2, 0, 0]}
        cellSize={4}
        sectionSize={20}
        cellColor={GRID_MINOR}
        sectionColor={GRID_MAJOR}
        fadeDistance={600}
        infiniteGrid
      />
      <Suspense fallback={null}>
        {/* key: refit the camera when switching views */}
        <Bounds key={assembly ? 'assembly' : 'enclosure'} fit clip observe margin={1.3}>
          {assembly ? (
            <Assembly url={assembly} selected={selected} onSelect={onSelect} />
          ) : (
            <>
              {base && <Part url={base} lid={false} />}
              {lid && <Part url={lid} lid />}
            </>
          )}
        </Bounds>
      </Suspense>
      <OrbitControls makeDefault />
      <GizmoHelper alignment="bottom-right" margin={[56, 56]}>
        <GizmoViewport axisColors={AXES} labelColor={BG} />
      </GizmoHelper>
    </Canvas>
  )
}
