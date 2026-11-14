// The enclosure STLs (enclosure frame, mm, Z up: see backend/contracts/base.py). The lid is
// exported in its closed position, so it is drawn see-through to show the base inside.
// assembly.glb (T25) is in the same frame, with the lid raised and every part placed.
import { Bounds, OrbitControls } from '@react-three/drei'
import { Canvas, useLoader } from '@react-three/fiber'
import { Suspense } from 'react'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { STLLoader } from 'three/addons/loaders/STLLoader.js'

function Part({ url, lid }: { url: string; lid: boolean }) {
  const geometry = useLoader(STLLoader, url)
  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial color={lid ? '#8fb3d9' : '#e8a33d'} transparent={lid} opacity={lid ? 0.35 : 1} />
    </mesh>
  )
}

function Assembly({ url }: { url: string }) {
  const gltf = useLoader(GLTFLoader, url)
  return <primitive object={gltf.scene} />
}

export default function Viewer3D({
  base,
  lid,
  assembly,
}: {
  base: string | null
  lid: string | null
  /** When set, show the assembly instead of the STLs. */
  assembly: string | null
}) {
  return (
    <Canvas camera={{ position: [120, -160, 140], up: [0, 0, 1], far: 5000 }}>
      <ambientLight intensity={0.7} />
      <directionalLight position={[100, -100, 200]} intensity={1.5} />
      <Suspense fallback={null}>
        {/* key: refit the camera when switching views */}
        <Bounds key={assembly ? 'assembly' : 'enclosure'} fit clip observe margin={1.3}>
          {assembly ? (
            <Assembly url={assembly} />
          ) : (
            <>
              {base && <Part url={base} lid={false} />}
              {lid && <Part url={lid} lid />}
            </>
          )}
        </Bounds>
      </Suspense>
      <OrbitControls makeDefault />
    </Canvas>
  )
}
