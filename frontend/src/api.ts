// The API calls the UI makes (backend/app/routers/runs.py and files.py, behind the /api proxy).
import { useEffect, useMemo, useReducer, useState } from 'react'
import type { AnswerRequest, EditRequest, Event as RunEvent, UserContext } from './contracts'
import { initialState, reduce, type RunState } from './state'

/** ?v busts the browser cache when a stage rewrites the same file. */
export const fileUrl = (runId: string, path: string, version: number) =>
  `/api/runs/${encodeURIComponent(runId)}/files/${path}?v=${version}`

/** `user` is the saved memory (owned parts, budget): the run plans around it. */
export async function startRun(prompt: string, files: File[], user: UserContext | null): Promise<string> {
  const body = new FormData()
  body.append('prompt', prompt)
  for (const file of files) body.append('files', file)
  if (user) body.append('user_context', JSON.stringify(user))
  const res = await fetch('/api/runs', { method: 'POST', body })
  if (!res.ok) throw new Error(`Starting the run failed (${res.status}): ${await res.text()}`)
  return ((await res.json()) as { run_id: string }).run_id
}

async function postJson(url: string, body: unknown): Promise<void> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`Sending it failed (${res.status}): ${await res.text()}`)
}

export const editRun = (runId: string, request: EditRequest) =>
  postJson(`/api/runs/${encodeURIComponent(runId)}/edit`, request)

export const answerQuestion = (runId: string, request: AnswerRequest) =>
  postJson(`/api/runs/${encodeURIComponent(runId)}/answer`, request)

export async function getMemory(): Promise<UserContext> {
  const res = await fetch('/api/memory')
  if (!res.ok) throw new Error(`Loading your parts failed (${res.status})`)
  return (await res.json()) as UserContext
}

/** Saves owned parts and budget; the API answers 422 for an unknown part id. */
export async function putMemory(user: UserContext): Promise<UserContext> {
  const res = await fetch('/api/memory', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(user),
  })
  if (!res.ok) throw new Error(`Saving your parts failed (${res.status}): ${await res.text()}`)
  return (await res.json()) as UserContext
}

export type Connection = 'live' | 'reconnecting' | 'lost'

/** Streams the run's events into the reducer. The stream starts at seq 1 on every mount (a page
 * refresh rebuilds the whole state); EventSource's own reconnects resume after Last-Event-ID. The
 * server ends the stream at `done` and EventSource reconnects on its own, so the events of a later
 * edit arrive too. `reconnect` reopens a stream EventSource gave up on (the reducer drops repeats). */
export function useRun(runId: string | null) {
  const [state, dispatch] = useReducer(reduce, initialState)
  const [connection, setConnection] = useState<Connection>('live')
  const [opened, setOpened] = useState(0)
  useEffect(() => {
    if (!runId) return
    const source = new EventSource(`/api/runs/${encodeURIComponent(runId)}/events`)
    source.onopen = () => setConnection('live')
    source.onmessage = (message) => {
      setConnection('live')
      dispatch(JSON.parse(message.data) as RunEvent)
    }
    source.onerror = () => setConnection(source.readyState === EventSource.CLOSED ? 'lost' : 'reconnecting')
    return () => source.close()
  }, [runId, opened])
  const reconnect = () => {
    setConnection('live')
    setOpened((n) => n + 1)
  }
  return { state, connection, reconnect }
}

export function useText(url: string | null): { text: string | null; error: string | null } {
  const [result, setResult] = useState<{ text: string | null; error: string | null }>({
    text: null,
    error: null,
  })
  useEffect(() => {
    if (!url) return
    let live = true
    fetch(url)
      .then((res) => (res.ok ? res.text() : Promise.reject(new Error(`${res.status} for ${url}`))))
      .then(
        (text) => live && setResult({ text, error: null }),
        (e: Error) => live && setResult({ text: null, error: e.message }),
      )
    return () => {
      live = false
    }
  }, [url])
  return result
}

/** useText for a JSON artifact: null until it has loaded. */
export function useJson<T>(url: string | null): T | null {
  const { text } = useText(url)
  return useMemo(() => (text === null ? null : (JSON.parse(text) as T)), [text])
}

/** Runs one request at a time and keeps its error for the form to show. */
export function useSend() {
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const send = async (request: () => Promise<unknown>): Promise<boolean> => {
    setSending(true)
    setError(null)
    try {
      await request()
      return true
    } catch (err) {
      setError((err as Error).message)
      return false
    } finally {
      setSending(false)
    }
  }
  return { sending, error, send }
}

export type Reply = ReturnType<typeof useReply>

/** What the composer and the quick replies send: the answer to the open question, or else an edit,
 * which waits until the run is idle (the API answers 409 while it works). */
export function useReply(
  state: RunState,
  onEdit: (instruction: string) => Promise<void>,
  onAnswer: (questionId: string, answer: string) => Promise<void>,
) {
  // lastSeq when the edit was accepted: stay busy until its first event arrives
  const [sentAt, setSentAt] = useState<number | null>(null)
  const [answered, setAnswered] = useState<{ id: string; text: string } | null>(null)
  const { sending, error, send: run } = useSend()
  const question = state.question
  const open = question !== null && answered?.id !== question.id
  const idle = state.done && sentAt !== state.lastSeq
  const send = async (text: string): Promise<boolean> => {
    if (question) {
      const ok = await run(() => onAnswer(question.id, text))
      if (ok) setAnswered({ id: question.id, text })
      return ok
    }
    const ok = await run(() => onEdit(text))
    if (ok) setSentAt(state.lastSeq)
    return ok
  }
  return {
    question,
    answer: question && answered?.id === question.id ? answered.text : null,
    ready: !sending && (open || (question === null && idle)),
    sending,
    error,
    send,
  }
}
