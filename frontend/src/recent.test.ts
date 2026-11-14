import { beforeEach, describe, expect, it } from 'vitest'
import { loadRecent, mergeRuns, remember } from './recent'

beforeEach(() => localStorage.clear())

describe('remember', () => {
  it('puts a new project first, and updates a listed one in place so the list stays in start order', () => {
    let list = remember([], { id: 'a', title: 'Plant monitor', at: 1 })
    list = remember(list, { id: 'b', title: 'Night light', at: 2 })
    expect(list.map((r) => r.id)).toEqual(['b', 'a'])
    list = remember(list, { id: 'a', status: 'Plan ready' }) // reopening an older project
    expect(list.map((r) => [r.id, r.at, r.status])).toEqual([
      ['b', 2, ''],
      ['a', 1, 'Plan ready'],
    ])
    expect(loadRecent()).toEqual(list)
  })
})

describe('mergeRuns', () => {
  it("adds the server's unknown runs, keeps this browser's entries, newest first", () => {
    const local = remember([], { id: 'a', title: 'Plant monitor', prompt: 'a plant monitor', at: 2_000_000 })
    const runs = [
      { run_id: 'a', title: 'Plant monitor', stage: 'done' as const, status: 'passed' as const, ts: 5000, spec_rev: 1 },
      { run_id: 'b', title: '', stage: 'firmware' as const, status: 'running' as const, ts: 3000, spec_rev: 0 },
      { run_id: 'c', title: 'Old lamp', stage: 'done' as const, status: 'failed' as const, ts: 1000, spec_rev: 2 },
    ]
    expect(mergeRuns(local, runs).map((r) => [r.id, r.title, r.status, r.prompt])).toEqual([
      ['b', 'New project', 'Planning…', ''],
      ['a', 'Plant monitor', '', 'a plant monitor'],
      ['c', 'Old lamp', 'Needs a look', ''],
    ])
  })
})
