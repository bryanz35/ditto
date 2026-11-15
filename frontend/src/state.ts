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
  /** Stages the engine marked stale and that haven't passed since: their files are out of date
   * (isStale), even when the rerun failed or was skipped. The checks panel shows each stage's own
   * status instead, so a failed rerun reads as failed. */
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
  // An event after done starts an edit's pipeline: earlier outcomes aren't retries of it.
  const stages: RunState['stages'] = state.done
    ? Object.fromEntries(Object.entries(state.stages).map(([stage, s]) => [stage, { ...s, attempts: [] }]))
    : state.stages
  const prev = stages[event.stage]
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
    stages: { ...stages, [event.stage]: stageState },
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

/** The project's conversation after the first prompt: the user's follow-ups and Ditto's replies
 * (events with data.chat, see backend/contracts/events.py). */
export const chatTurns = (state: RunState): Event[] =>
  state.log.filter((e) => e.data.chat === 'user' || e.data.chat === 'agent')

/** The agent's current turn, for the chat status line: when the user's latest message arrived
 * (Unix s) and the tokens the agent has used on it so far (data.tokens), or null if none yet. */
export function turnUsage(state: RunState): { since: number; tokens: number | null } | null {
  const turn = chatTurns(state).at(-1)
  if (turn?.data.chat !== 'user') return null
  const last = state.log.findLast((e) => e.seq > turn.seq && e.data.tokens)
  const t = last?.data.tokens as { input: number; output: number } | undefined
  return { since: turn.ts, tokens: t ? t.input + t.output : null }
}

const GENERIC = ['Dittoing…', 'Planning…', 'Thinking it through…']
// Plain words for a stage, for "Fixing a problem with the …".
const NOUN: Partial<Record<Stage, string>> = {
  validate: 'wiring',
  layout: 'layout',
  enclosure: 'case',
  assembly: 'case',
  firmware: 'code',
  wiring: 'wiring',
  simulate: 'code',
  bom: 'prices',
  checks: 'checks',
}
const DOING: Partial<Record<Stage, string>> = {
  validate: 'Checking the wiring…',
  wiring: 'Checking the wiring…',
  firmware: 'Writing and testing the code…',
  simulate: 'Writing and testing the code…',
  layout: 'Designing the case…',
  enclosure: 'Designing the case…',
  assembly: 'Designing the case…',
  bom: 'Finding prices…',
  checks: 'Checking everything…',
}

/** The line next to Ditto's sprite (Figma "Spec · Ditto status line"): what it is doing right now,
 * from the latest event. `tick` rotates the generic lines while there is nothing specific to say. */
export function statusLine(state: RunState, project: string | null, tick = 0): string {
  if (state.question) return 'Ditto has a question for you'
  const last = state.log.at(-1)
  const generic = GENERIC[tick % GENERIC.length]
  if (!last || last.stage === 'done' || last.data.chat) return generic // a chat turn says nothing about the work
  const stage = state.stages[last.stage]!
  if (stage.status === 'failed' || (stage.status === 'running' && (stage.attempt ?? 1) > 1)) {
    return `Fixing a problem with the ${NOUN[last.stage] ?? last.stage}…`
  }
  if (last.stage === 'plan') return project ? `Picking parts for your ${project.toLowerCase()}…` : generic
  return DOING[last.stage] ?? generic
}
