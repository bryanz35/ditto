// Start · Dashboard: "What do you want to build?" and the prompt composer (Figma 7:2).
import { useState } from 'react'
import { useSend } from './api'
import ditto from './assets/ditto.png'
import { Icon, Segmented } from './Icon'
import { LEVELS, type Level } from './recent'
import { enterSends } from './ui'

export function Start({
  level,
  onLevel,
  onStart,
}: {
  level: Level
  onLevel: (level: Level) => void
  onStart: (prompt: string, files: File[]) => Promise<void>
}) {
  const [prompt, setPrompt] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const { sending, error, send } = useSend()
  const submit = () => {
    if (prompt.trim() && !sending) void send(() => onStart(prompt, files))
  }

  return (
    <main className="start">
      <div className="start-col">
        <div className="ditto-art">
          <img src={ditto} alt="" />
        </div>
        <h1>What do you want to build?</h1>
        <form
          className="composer start-composer"
          onSubmit={(e) => {
            e.preventDefault()
            submit()
          }}
        >
          <textarea
            aria-label="Describe what you want to make"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={enterSends(submit)}
            placeholder="Describe what you want to make. For example: a plant monitor that beeps when the soil is dry, for under $30."
            rows={3}
          />
          {files.length > 0 && (
            <ul className="attached">
              {files.map((f) => (
                <li key={f.name}>
                  <Icon name="image" /> {f.name}
                </li>
              ))}
            </ul>
          )}
          <div className="toolbar">
            <label className="btn">
              <Icon name="image-plus" />
              Add image
              <input
                type="file"
                accept="image/*,video/*"
                multiple
                hidden
                onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
              />
            </label>
            <span className="vdivider" />
            <span className="level">
              I am a
              <Segmented label="Skill level" options={LEVELS} value={level} onChange={onLevel} />
            </span>
            <span className="spacer" />
            <button type="submit" className="btn primary" disabled={sending || !prompt.trim()}>
              <Icon name="arrow-up" />
              {sending ? 'Starting…' : 'Plan it'}
            </button>
          </div>
        </form>
        {error && <p role="alert">{error}</p>}
        <div className="hints">
          <span>Enter to send · Shift + Enter for a new line</span>
          <span>Photos and sketches: JPG, PNG or HEIC</span>
        </div>
      </div>
    </main>
  )
}
