import { lazy, Suspense, useState } from 'react'
import { answerQuestion, editRun, fileUrl, startRun, useRun } from './api'
import { BomTab, ChatPanel, ChecksPanel, CodeTab, SimulationTab, WiringTab } from './panels'
import { isStale } from './state'

// three.js is big; load it only when the 3D tab first renders.
const Viewer3D = lazy(() => import('./Viewer3D'))

const TABS = ['3D', 'Wiring', 'BOM', 'Code', 'Simulation'] as const
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
  const { state, connection, reconnect } = useRun(runId)
  const [tab, setTab] = useState<Tab>('3D')
  const [assemblyView, setAssemblyView] = useState(false)
  const urlOf = (name: string) => {
    const a = state.artifacts[name]
    return a && runId ? fileUrl(runId, a.path, a.seq) : null
  }
  const staleOf = (name: string) => isStale(state, name)
  const sim = state.stages.simulate
  const tabs = TABS.filter((t) => t !== 'Simulation' || (sim && sim.status !== 'skipped'))
  // The assembly preview exists once T25's stage has produced it; until then only the STLs.
  const assembly = urlOf('assembly_glb')
  const shown3D = assembly && assemblyView ? 'assembly_glb' : 'base_stl'

  return (
    <div className="app">
      <ChatPanel
        state={state}
        onStart={onStart}
        onEdit={runId ? (instruction) => editRun(runId, { instruction }) : null}
        onAnswer={(question_id, answer) => answerQuestion(runId!, { question_id, answer })}
      />
      <main className="work">
        {connection === 'lost' ? (
          <p className="banner" role="alert">
            Lost the connection to this run.{' '}
            <button type="button" onClick={reconnect}>
              Retry
            </button>
          </p>
        ) : (
          // the server closes the stream at done and EventSource reopens it: not worth a banner
          connection === 'reconnecting' &&
          !state.done && (
            <p className="banner" role="status">
              Reconnecting to the run…
            </p>
          )
        )}
        <nav role="tablist">
          {tabs.map((t) => (
            <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>
              {t}
            </button>
          ))}
        </nav>
        <div role="tabpanel" className={`panel tab-${tab}`}>
          {tab === '3D' &&
            (urlOf('base_stl') ? (
              <>
                {assembly && (
                  <div className="toggle" role="group" aria-label="3D view">
                    <button type="button" aria-pressed={!assemblyView} onClick={() => setAssemblyView(false)}>
                      Enclosure
                    </button>
                    <button type="button" aria-pressed={assemblyView} onClick={() => setAssemblyView(true)}>
                      Assembly
                    </button>
                  </div>
                )}
                {staleOf(shown3D) && (
                  <p className="stale-note">
                    <span className="badge stale">stale</span> Out of date: the spec changed since this was built.
                  </p>
                )}
                <Suspense fallback={<p className="empty">Loading the 3D view…</p>}>
                  <Viewer3D
                    base={urlOf('base_stl')}
                    lid={urlOf('lid_stl')}
                    assembly={shown3D === 'assembly_glb' ? assembly : null}
                  />
                </Suspense>
              </>
            ) : (
              <p className="empty">Not built yet.</p>
            ))}
          {tab === 'Wiring' && <WiringTab url={urlOf('wiring_json')} stale={staleOf('wiring_json')} />}
          {tab === 'BOM' && <BomTab url={urlOf('bom_json')} stale={staleOf('bom_json')} />}
          {tab === 'Code' && <CodeTab urlOf={urlOf} staleOf={staleOf} />}
          {tab === 'Simulation' && sim && <SimulationTab stage={sim} urlOf={urlOf} staleOf={staleOf} />}
        </div>
        <ChecksPanel state={state} />
      </main>
    </div>
  )
}
