// Bare page for Gate G0: shows the fixture run streaming from the API. T15 replaces it with the real UI.
import { useEffect, useState } from 'react'
import type { Event as RunEvent } from './contracts'

export default function App() {
  const [events, setEvents] = useState<RunEvent[]>([])

  useEffect(() => {
    const source = new EventSource('/api/runs/fixture/events')
    source.onmessage = (message) => {
      const event = JSON.parse(message.data) as RunEvent
      setEvents((previous) => [...previous, event])
      if (event.stage === 'done') source.close()
    }
    return () => source.close()
  }, [])

  return (
    <main>
      <h1>Prompt-to-Device</h1>
      <ol>
        {events.map((e) => (
          <li key={e.seq}>
            {e.stage} · {e.status} · {e.message}
          </li>
        ))}
      </ol>
    </main>
  )
}
