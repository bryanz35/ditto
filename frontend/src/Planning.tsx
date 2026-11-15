// Project · Planning: the prompt as a chat turn and Ditto at work under it (Figma 11:142).
import { useEffect, useState } from 'react'
import Markdown from 'react-markdown'
import { useSend, type Reply } from './api'
import { Icon, type IconName } from './Icon'
import { QuestionCard } from './panels'
import { ago, type Recent } from './recent'
import { chatTurns, statusLine, type RunState } from './state'
import { enterSends, soon } from './ui'

/** Seconds since epoch, ticking once a second. */
function useNow(): number {
  const [now, setNow] = useState(() => Date.now() / 1000)
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now() / 1000), 1000)
    return () => clearInterval(timer)
  }, [])
  return now
}

const TODO_ICON: Record<string, IconName> = { completed: 'check', in_progress: 'loader', pending: 'circle-small' }

const mb = (bytes: number) => `${(bytes / 1e6).toFixed(1)} MB`

export function Planning({
  state,
  title,
  project,
  entry,
  reply,
  onDetails,
  onStop,
}: {
  state: RunState
  title: string
  /** spec.title once the plan has one */
  project: string | null
  entry: Recent | null
  reply: Reply
  onDetails: () => void
  /** Cancels the run (POST /runs/{id}/cancel). */
  onStop: () => Promise<void>
}) {
  const now = useNow()
  const first = state.log[0]
  const last = state.log.at(-1)
  // A replayed run carries its old timestamps: then show how long it took, not how long ago it was.
  const end = last && now - last.ts < 600 ? Math.max(now, last.ts) : last?.ts
  const elapsed = first && end ? Math.max(0, Math.floor(end - first.ts)) : 0
  const clock = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, '0')}`

  return (
    <main className="planning">
      <header className="project-header">
        <span className="name">{title}</span>
        {entry?.level && <span className="tag">{entry.level}</span>}
        <span className="spacer" />
        <button type="button" className="icon-btn" aria-label="Details" onClick={onDetails}>
          <Icon name="ellipsis" />
        </button>
      </header>
      <div className="thread">
        <div className="thread-col">
          {entry?.prompt && (
            <div className="user-turn">
              <div className="user-msg">
                {entry.files.map((f) => (
                  <div key={f.name} className="attachment">
                    <span className="thumb">
                      <Icon name="image" />
                    </span>
                    <span className="file">
                      <span className="name">{f.name}</span>
                      <span className="detail">Sketch · {mb(f.size)}</span>
                    </span>
                  </div>
                ))}
                <p>{entry.prompt}</p>
              </div>
              <p className="turn-meta">
                You{entry.level && ` · ${entry.level}`} · {ago(entry.at)}
              </p>
            </div>
          )}
          {chatTurns(state).map((e) =>
            e.data.chat === 'user' ? (
              <div key={e.seq} className="user-turn">
                <div className="user-msg">
                  <p>{e.message}</p>
                </div>
                <p className="turn-meta">You</p>
              </div>
            ) : (
              <div key={e.seq} className="agent-turn">
                <div className="md">
                  <Markdown>{e.message}</Markdown>
                </div>
                <p className="turn-meta">Ditto</p>
              </div>
            ),
          )}
          {!state.done && (
            <div className="thinking">
              <div className="sprite" aria-hidden="true" />
              <div className="status">
                <p className="status-line">
                  {statusLine(state, project, Math.floor(now / 3))}
                </p>
                <p className="mono">Dittoing · {clock}</p>
                {state.todos.length > 0 && (
                  <ul className="steps" aria-label="Plan">
                    {state.todos.map((t) => (
                      <li key={t.content} className={t.status}>
                        <Icon name={TODO_ICON[t.status]} />
                        {t.content}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
          <QuestionCard reply={reply} />
        </div>
      </div>
      <Composer reply={reply} done={state.done} onStop={onStop} />
    </main>
  )
}

/** The docked composer while Ditto works: answers its question; changes open once the plan is ready. */
function Composer({ reply, done, onStop }: { reply: Reply; done: boolean; onStop: () => Promise<void> }) {
  const stop = useSend()
  const [text, setText] = useState('')
  const submit = async () => {
    if (text.trim() && reply.ready && (await reply.send(text))) setText('')
  }
  return (
    <div className="dock">
      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault()
          void submit()
        }}
      >
        <textarea
          aria-label={reply.question ? 'Your answer' : 'Message Ditto'}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={enterSends(() => void submit())}
          placeholder="Ask Ditto a question, or tell it what to change…"
          rows={1}
        />
        <div className="toolbar">
          {/* shortcut: an edit carries text only (EditRequest has no files) */}
          <button type="button" className="btn" {...soon(null)}>
            <Icon name="image-plus" />
            Add image
          </button>
          <span className="spacer" />
          {(reply.question || done) && (
            <button type="submit" className="btn primary" disabled={!reply.ready || !text.trim()}>
              <Icon name="arrow-up" />
              {reply.question ? 'Answer' : 'Send'}
            </button>
          )}
          <button type="button" className="btn secondary" disabled={stop.sending || done} onClick={() => void stop.send(onStop)}>
            <Icon name="square" />
            Stop
          </button>
        </div>
      </form>
      {(reply.error ?? stop.error) && <p role="alert">{reply.error ?? stop.error}</p>}
      <p className="footnote">Ditto checks every part, wire, line of code and case with code before you see it.</p>
    </div>
  )
}
