import { describe, expect, it } from 'vitest'
import runJsonl from '../../fixtures/events/plant_monitor.jsonl?raw'
import editJsonl from '../../fixtures/events/plant_monitor_edit.jsonl?raw'
import type { Event } from './contracts'
import { initialState, isStale, reduce } from './state'

const parseJsonl = (text: string): Event[] =>
  text
    .split('\n')
    .filter((l) => l.trim())
    .map((l) => JSON.parse(l) as Event)

const run = parseJsonl(runJsonl)
const edit = parseJsonl(editJsonl)
const fold = (events: Event[], state = initialState) => events.reduce(reduce, state)

describe('reduce', () => {
  it('folds the plant_monitor fixture into a finished run', () => {
    const s = fold(run)
    for (const stage of [
      'plan', 'validate', 'layout', 'enclosure', 'assembly',
      'firmware', 'wiring', 'simulate', 'bom', 'checks', 'done',
    ] as const) {
      expect(s.stages[stage]?.status, stage).toBe('passed')
    }
    expect(s.stages.validate?.attempts.map((a) => [a.status, a.attempt])).toEqual([
      ['failed', 1],
      ['passed', 2],
    ])
    expect(s.stages.validate?.attempts[0].errors[0].code).toBe('pin_conflict')
    expect(Object.keys(s.artifacts)).toEqual(
      expect.arrayContaining([
        'base_stl', 'lid_stl', 'wiring_json', 'bom_json', 'main_cpp', 'pins_h', 'platformio_ini',
      ]),
    )
    expect(s.specRev).toBe(2)
    expect(s.done).toBe(true)
    expect(s.question).toBeNull()
    expect(s.todos.every((t) => t.status === 'completed')).toBe(true)
  })

  it('keeps the attempt number of a stage being retried', () => {
    expect(fold(run.slice(0, 5)).stages.validate?.attempt).toBe(1)
    expect(fold(run.slice(0, 6)).stages.validate?.attempt).toBe(2)
    expect(fold(run.slice(0, 9)).stages.layout?.attempt).toBeNull()
  })

  it('holds the question until its stage moves on', () => {
    const s = fold(run.slice(0, 2))
    expect(s.question?.id).toBe('q1')
    expect(fold(run.slice(2, 3), s).question).toBeNull()
  })

  it('marks artifacts stale after an edit until their stage passes again', () => {
    const before = fold(run)
    const marked = fold(edit.filter((e) => e.seq <= 32), before)
    expect(marked.specRev).toBe(3)
    expect(marked.done).toBe(false)
    expect(isStale(marked, 'base_stl')).toBe(true)
    expect(isStale(marked, 'layout_json')).toBe(true)
    expect(isStale(marked, 'main_cpp')).toBe(false) // firmware isn't affected by wall_mm
    const after = fold(edit, before)
    expect(isStale(after, 'base_stl')).toBe(false)
    expect(after.artifacts.base_stl.spec_rev).toBe(3)
    expect(after.done).toBe(true)
  })

  it("starts each edit's attempt history afresh: a rerun isn't a retry", () => {
    const after = fold(edit, fold(run))
    expect(after.stages.enclosure?.attempts.map((a) => a.message)).toEqual(['Watertight, fits the generic printer'])
    expect(after.stages.done?.attempts).toHaveLength(1)
    expect(after.stages.validate?.attempts).toEqual([]) // not rerun by this edit
    expect(after.stages.validate?.status).toBe('passed')
  })

  it('ignores events it already has, so a replayed stream is harmless', () => {
    const half = fold(run.slice(0, 12))
    expect(fold(run, half)).toEqual(fold(run))
  })
})
