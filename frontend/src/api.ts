// The API calls the UI makes (backend/app/routers/runs.py and files.py, behind the /api proxy).
import { useEffect, useReducer, useState } from 'react'
import type { AnswerRequest, EditRequest, Event as RunEvent } from './contracts'
import { initialState, reduce } from './state'

/** ?v busts the browser cache when a stage rewrites the same file. */
export const fileUrl = (runId: string, path: string, version: number) =>
  `/api/runs/${encodeURIComponent(runId)}/files/${path}?v=${version}`

export async function startRun(prompt: string, files: File[]): Promise<string> {
  const body = new FormData()
  body.append('prompt', prompt)
  for (const file of files) body.append('files', file)
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
