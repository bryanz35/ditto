// The API calls the UI makes (backend/app/routers/runs.py and files.py, behind the /api proxy).
import { useEffect, useReducer, useState } from 'react'
import type { Event as RunEvent } from './contracts'
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

/** Streams the run's events into the reducer. The stream starts at seq 1 on every mount (a page
 * refresh rebuilds the whole state); EventSource's own reconnects resume after Last-Event-ID. The
 * stream stays open after `done`, so the events of a later edit arrive too. */
export function useRun(runId: string | null) {
  const [state, dispatch] = useReducer(reduce, initialState)
  useEffect(() => {
    if (!runId) return
    const source = new EventSource(`/api/runs/${encodeURIComponent(runId)}/events`)
    source.onmessage = (message) => dispatch(JSON.parse(message.data) as RunEvent)
    return () => source.close()
  }, [runId])
  return state
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
