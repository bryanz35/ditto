// The enclosure STLs (enclosure frame, mm, Z up: see backend/contracts/base.py). The lid is
// exported in its closed position, so it is drawn see-through to show the base inside.
import { Bounds, OrbitControls } from '@react-three/drei'
import { Canvas, useLoader } from '@react-three/fiber'
import { Suspense } from 'react'
import { STLLoader } from 'three/addons/loaders/STLLoader.js'

function Part({ url, lid }: { url: string; lid: boolean }) {
  const geometry = useLoader(STLLoader, url)
  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial color={lid ? '#8fb3d9' : '#e8a33d'} transparent={lid} opacity={lid ? 0.35 : 1} />
    </mesh>
  )
}

export default function Viewer3D({ base, lid }: { base: string | null; lid: string | null }) {
  return (
    <Canvas camera={{ position: [120, -160, 140], up: [0, 0, 1], far: 5000 }}>
      <ambientLight intensity={0.7} />
      <directionalLight position={[100, -100, 200]} intensity={1.5} />
      <Suspense fallback={null}>
        <Bounds fit clip observe margin={1.3}>
          {base && <Part url={base} lid={false} />}
          {lid && <Part url={lid} lid />}
        </Bounds>
      </Suspense>
      <OrbitControls makeDefault />
    </Canvas>
  )
}
