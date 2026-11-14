import { useCallback, useEffect, useState } from 'react'
import { Build } from './Build'
import { answerQuestion, cancelRun, editRun, listRuns, fileUrl, getMemory, putMemory, startRun, useJson, useReply, useRun } from './api'
import type { ProjectSpec, UserContext } from './contracts'
import { MyParts } from './MyParts'
import { Overview } from './Overview'
import { Details } from './panels'
import { Planning } from './Planning'
import { loadRecent, mergeRuns, remember, type Level, type Recent } from './recent'
import { Shell, type Page } from './Shell'
import { Start } from './Start'
import { isStale, type RunState } from './state'

export default function App() {
  // The run id lives in the URL so a refresh reopens the same run's stream.
  const [runId, setRunId] = useState(() => new URLSearchParams(location.search).get('run'))
  const [page, setPage] = useState<Page>('home')
  const [level, setLevel] = useState<Level>('Beginner')
  const [recent, setRecent] = useState(loadRecent)
  const [memory, setMemory] = useState<UserContext | null>(null)
  useEffect(() => {
    getMemory().then(setMemory, () => {}) // no memory API: the kit count just stays hidden
    listRuns().then((runs) => setRecent((list) => mergeRuns(list, runs)), () => {}) // no list: this browser's only
  }, [])
  const note = useCallback((change: Partial<Recent> & { id: string }) => setRecent((list) => remember(list, change)), [])

  const open = (id: string | null) => {
    history.replaceState(null, '', id ? `?run=${encodeURIComponent(id)}` : location.pathname)
    setRunId(id)
    setPage('home')
  }
  const start = async (prompt: string, files: File[]) => {
    const id = await startRun(prompt, files, { ...memory, level: level.toLowerCase() as UserContext['level'] })
    note({ id, title: prompt.trim().slice(0, 60), prompt, files: files.map((f) => ({ name: f.name, size: f.size })), level, status: 'Planning…', at: Date.now() })
    open(id)
  }
  const save = async (next: UserContext) => {
    const saved = await putMemory(next)
    setMemory(saved)
    return saved
  }
  // read-modify-write on a fresh copy, so another tab's changes aren't lost
  const own = async (partId: string) => {
    const now = await getMemory()
    await save({ ...now, owned: { ...now.owned, [partId]: (now.owned[partId] ?? 0) + 1 } })
  }
  const kit = memory && Object.values(memory.owned).reduce((a, b) => a + b, 0)
  const shell = { page, runId, recent, kit, name: memory?.name ?? null, onPage: setPage, onOpen: open }

  if (page === 'parts') {
    return (
      <Shell {...shell}>
        {/* key: start the form over once the saved memory has loaded */}
        <MyParts key={memory ? 'loaded' : 'empty'} memory={memory} onSave={save} />
      </Shell>
    )
  }
  if (!runId) {
    return (
      <Shell {...shell}>
        <Start level={level} onLevel={setLevel} onStart={start} />
      </Shell>
    )
  }
  // key: a new run starts from a fresh state
  return (
    <Workspace
      key={runId}
      runId={runId}
      entry={recent.find((r) => r.id === runId) ?? null}
      note={note}
      onOwn={own}
      onExit={() => open(null)}
      shell={shell}
    />
  )
}

/** Where the project is up to, for the Recent list. */
const progress = (state: RunState, planned: boolean) =>
  !planned ? 'Planning…' : !state.done ? 'Updating…' : state.stages.checks?.status === 'passed' ? 'Plan ready' : 'Needs a look'

function Workspace({
  runId,
  entry,
  note,
  onOwn,
  onExit,
  shell,
}: {
  runId: string
  entry: Recent | null
  note: (change: Partial<Recent> & { id: string }) => void
  onOwn: (partId: string) => Promise<void>
  onExit: () => void
  shell: Omit<Parameters<typeof Shell>[0], 'children'>
}) {
  const { state, connection, reconnect } = useRun(runId)
  const [details, setDetails] = useState(false)
  const [building, setBuilding] = useState(false)
  const urlOf = (name: string) => {
    const a = state.artifacts[name]
    return a ? fileUrl(runId, a.path, a.seq) : null
  }
  const staleOf = (name: string) => isStale(state, name)
  const spec = useJson<ProjectSpec>(urlOf('spec'))
  const reply = useReply(
    state,
    (instruction) => editRun(runId, { instruction }),
    (question_id, answer) => answerQuestion(runId, { question_id, answer }),
  )
  // The overview takes over once the first pipeline is done, and stays up while edits rerun.
  const planned = state.log.some((e) => e.stage === 'done')
  const title = spec?.title ?? entry?.title ?? 'New project'
  const status = progress(state, planned)
  const started = state.lastSeq > 0
  // a run opened from a link has no entry yet: take its prompt from the spec
  const prompt = entry?.prompt ? null : (spec?.prompt ?? null)
  useEffect(() => {
    if (started) note({ id: runId, title, status, ...(prompt && { prompt }) })
  }, [note, runId, started, title, status, prompt])

  const banner =
    connection === 'lost' ? (
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
    )
  const drawer = details && (
    <Details state={state} urlOf={urlOf} staleOf={staleOf} onClose={() => setDetails(false)} />
  )

  if (planned && building) {
    return <Build runId={runId} title={title} spec={spec} urlOf={urlOf} onBack={() => setBuilding(false)} onExit={onExit} />
  }
  if (planned) {
    return (
      <>
        <Overview
          state={state}
          title={title}
          spec={spec}
          urlOf={urlOf}
          staleOf={staleOf}
          reply={reply}
          onOwn={onOwn}
          onDetails={() => setDetails(true)}
          onBuild={() => setBuilding(true)}
          onExit={onExit}
        />
        {banner}
        {drawer}
      </>
    )
  }
  return (
    <Shell {...shell}>
      <Planning
        state={state}
        title={title}
        project={spec?.title ?? null}
        entry={entry}
        reply={reply}
        onDetails={() => setDetails(!details)}
        onStop={() => cancelRun(runId)}
      />
      {banner}
      {drawer}
    </Shell>
  )
}
