import { beforeEach, describe, expect, it } from 'vitest'
import { loadRecent, remember } from './recent'

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
