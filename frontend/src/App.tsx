import { lazy, Suspense, useState } from 'react'
import { fileUrl, startRun, useRun } from './api'
import { BomTab, ChatPanel, ChecksPanel, CodeTab, WiringTab } from './panels'
import { isStale } from './state'

// three.js is big; load it only when the 3D tab first renders.
const Viewer3D = lazy(() => import('./Viewer3D'))

const TABS = ['3D', 'Wiring', 'BOM', 'Code'] as const
type Tab = (typeof TABS)[number]

export default function App() {
  // The run id lives in the URL so a refresh reopens the same run's stream.
  const [runId, setRunId] = useState(() => new URLSearchParams(location.search).get('run'))

  const start = async (prompt: string, files: File[]) => {
    const id = await startRun(prompt, files)
    history.replaceState(null, '', `?run=${encodeURIComponent(id)}`)
    setRunId(id)
  }

  // key: a new run starts from a fresh state
  return <Workspace key={runId ?? ''} runId={runId} onStart={start} />
}

function Workspace({
  runId,
  onStart,
}: {
  runId: string | null
  onStart: (prompt: string, files: File[]) => Promise<void>
}) {
  const state = useRun(runId)
  const [tab, setTab] = useState<Tab>('3D')
  const urlOf = (name: string) => {
    const a = state.artifacts[name]
    return a && runId ? fileUrl(runId, a.path, a.seq) : null
  }
  const staleOf = (name: string) => isStale(state, name)

  return (
    <div className="app">
      <ChatPanel state={state} onStart={onStart} />
      <main className="work">
        <nav role="tablist">
          {TABS.map((t) => (
            <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>
              {t}
            </button>
          ))}
        </nav>
        <div role="tabpanel" className={`panel tab-${tab}`}>
          {tab === '3D' &&
            (urlOf('base_stl') ? (
              <>
                {staleOf('base_stl') && <p className="stale-note">Out of date: the spec changed since this was built.</p>}
                <Suspense fallback={<p className="empty">Loading the 3D view…</p>}>
                  <Viewer3D base={urlOf('base_stl')} lid={urlOf('lid_stl')} />
                </Suspense>
              </>
            ) : (
              <p className="empty">Not built yet.</p>
            ))}
          {tab === 'Wiring' && <WiringTab url={urlOf('wiring_json')} stale={staleOf('wiring_json')} />}
          {tab === 'BOM' && <BomTab url={urlOf('bom_json')} stale={staleOf('bom_json')} />}
          {tab === 'Code' && <CodeTab urlOf={urlOf} staleOf={staleOf} />}
        </div>
        <ChecksPanel state={state} />
      </main>
    </div>
  )
}
