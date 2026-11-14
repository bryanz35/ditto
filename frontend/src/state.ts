// Run state: a pure fold over the run's Events (see backend/contracts/events.py).
import type { Event, Question, Todo, ToolError } from './contracts'

export type Stage = Event['stage']
export type Status = Event['status']

// Pipeline order, same as STAGES in backend/contracts/events.py.
export const STAGES: Stage[] = [
  'plan',
  'validate',
  'layout',
  'enclosure',
  'assembly',
  'firmware',
  'wiring',
  'simulate',
  'bom',
  'checks',
  'done',
]

export interface Attempt {
  status: Status
  attempt: number | null
  message: string
  errors: ToolError[]
}

export interface StageState {
  status: Status
  message: string
  errors: ToolError[]
  spec_rev: number
  /** 1-based retry counter of the latest event (data.attempt), if the stage sends one. */
  attempt: number | null
  /** Finished outcomes (passed, failed, skipped) in order, so a retried stage shows its history. */
  attempts: Attempt[]
}

export interface Artifact {
  path: string
  stage: Stage
  spec_rev: number
  /** Seq of the event that produced it: changes whenever the file is rewritten. */
  seq: number
}

export interface RunState {
  lastSeq: number
  /** Rev of the saved spec.json: the spec_rev of the latest event carrying the "spec" artifact. */
  specRev: number
  stages: Partial<Record<Stage, StageState>>
  artifacts: Record<string, Artifact>
  /** Stages the engine marked stale and that haven't passed since. */
  stale: Stage[]
  todos: Todo[]
  question: (Question & { stage: Stage }) | null
  done: boolean
  log: Event[]
}

export const initialState: RunState = {
  lastSeq: 0,
  specRev: 0,
  stages: {},
  artifacts: {},
  stale: [],
  todos: [],
  question: null,
  done: false,
  log: [],
}

const FINISHED: Status[] = ['passed', 'failed', 'skipped']

export function reduce(state: RunState, event: Event): RunState {
  // A reconnect or a page refresh replays events we already have.
  if (event.seq <= state.lastSeq) return state
  const prev = state.stages[event.stage]
  const attempt = typeof event.data.attempt === 'number' ? event.data.attempt : null
  const attempts = prev?.attempts ?? []
  const stageState: StageState = {
    status: event.status,
    message: event.message,
    errors: event.errors,
    spec_rev: event.spec_rev,
    attempt,
    attempts: FINISHED.includes(event.status)
      ? [...attempts, { status: event.status, attempt, message: event.message, errors: event.errors }]
      : attempts,
  }
  const artifacts = { ...state.artifacts }
  for (const [name, path] of Object.entries(event.artifacts)) {
    artifacts[name] = { path, stage: event.stage, spec_rev: event.spec_rev, seq: event.seq }
  }
  let stale = state.stale
  if (event.status === 'stale' && !stale.includes(event.stage)) stale = [...stale, event.stage]
  if (event.status === 'passed') stale = stale.filter((s) => s !== event.stage)

  let question = state.question
  if (event.status === 'waiting' && event.data.question) {
    question = { ...(event.data.question as Question), stage: event.stage }
  } else if (question?.stage === event.stage) {
    question = null
  }

  return {
    lastSeq: event.seq,
    specRev: 'spec' in event.artifacts ? event.spec_rev : state.specRev,
    stages: { ...state.stages, [event.stage]: stageState },
    artifacts,
    stale,
    todos: Array.isArray(event.data.todos) ? (event.data.todos as Todo[]) : state.todos,
    question,
    done: event.stage === 'done',
    log: [...state.log, event],
  }
}

export function isStale(state: RunState, name: string): boolean {
  const a = state.artifacts[name]
  return a !== undefined && state.stale.includes(a.stage)
}
