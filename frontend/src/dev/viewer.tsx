// Dev-only 3D playground (`npm run dev`, then /viewer.html): the device and every build step's
// animation without running a plan. Not part of the app build (vite only builds index.html).
//   /viewer.html                the plant_monitor fixture
//   /viewer.html?run=<run_id>   a real run's files, through the API (backend running)
// In the console, window.__device is the scene (scene/device.ts).
import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import fixtureGlb from '../../../fixtures/runs/plant_monitor/cad/assembly.glb?url'
import fixtureLayout from '../../../fixtures/runs/plant_monitor/cad/layout.json?raw'
import fixtureManifest from '../../../fixtures/runs/plant_monitor/cad/manifest.json?raw'
import fixtureSpec from '../../../fixtures/runs/plant_monitor/spec.json?raw'
import fixtureWiring from '../../../fixtures/runs/plant_monitor/wiring.json?raw'
import type { EnclosureManifest, Layout, ProjectSpec, Wiring } from '../contracts'
import { buildSteps } from '../guide'
import '../index.css'
import Viewer3D from '../Viewer3D'

const run = new URLSearchParams(location.search).get('run')
const file = (path: string) => `/api/runs/${run}/files/${path}`
const load = async <T,>(path: string, fixture: string): Promise<T> =>
  JSON.parse(run ? await (await fetch(file(path))).text() : fixture) as T

const [spec, layout, wiring, manifest] = await Promise.all([
  load<ProjectSpec>('spec.json', fixtureSpec),
  load<Layout>('cad/layout.json', fixtureLayout),
  load<Wiring>('wiring.json', fixtureWiring),
  load<EnclosureManifest>('cad/manifest.json', fixtureManifest),
])
const glb = run ? file('cad/assembly.glb') : fixtureGlb
const steps = buildSteps({ spec, layout, wiring, bom: null, enclosure: manifest, urlOf: () => null })

export function Playground() {
  const [at, setAt] = useState(-1) // -1: the overview
  const [exploded, setExploded] = useState(false)
  const step = steps[at]
  return (
    <main style={{ position: 'fixed', inset: 0 }}>
      <Viewer3D
        base={null}
        lid={null}
        assembly={glb}
        spec={spec}
        wiring={wiring}
        manifest={manifest}
        exploded={exploded}
        build={at >= 0 ? { steps, index: at } : null}
        selected={step?.ref && step.kind !== 'Code' ? { ref: step.ref, label: step.noun ?? step.ref } : null}
      />
      <nav
        className="view-toolbar"
        style={{ left: 16, right: 'auto', flexWrap: 'wrap', maxWidth: 'calc(100% - 32px)' }}
      >
        <button type="button" className={`btn ${at < 0 ? 'primary' : ''}`} onClick={() => setAt(-1)}>
          Overview
        </button>
        {at < 0 && (
          <button type="button" className="btn" onClick={() => setExploded((x) => !x)}>
            {exploded ? 'Assemble' : 'Explode'}
          </button>
        )}
        {steps.map((s, i) => (
          <button key={s.id} type="button" className={`btn ${i === at ? 'primary' : ''}`} onClick={() => setAt(i)}>
            {i + 1} {s.label}
          </button>
        ))}
      </nav>
    </main>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Playground />
  </StrictMode>,
)
