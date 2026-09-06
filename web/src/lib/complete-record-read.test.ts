import { describe, expect, it, vi } from 'vitest'
import { readCompleteRecords } from './complete-record-read'

describe('complete public record reads', () => {
  it('follows the actual returned count when a server cap is smaller than requested', async () => {
    const rows = Array.from({ length: 7 }, (_, i) => ({ id: String(i) }))
    const read = vi.fn(async (from: number) => ({ data: rows.slice(from, from + 2), count: rows.length, error: null }))
    expect(await readCompleteRecords('Test', read)).toEqual(rows)
    expect(read.mock.calls.map(([from]) => from)).toEqual([0, 2, 4, 6])
  })
  it.each([
    { data: null, count: 0, error: new Error('timeout') },
    { data: [], count: null, error: null },
    { data: [{ id: 'x' }, { id: 'x' }], count: 2, error: null },
    { data: [], count: 1, error: null },
    { data: [], count: 10001, error: null },
  ])('rejects unavailable or incomplete reads instead of manufacturing zeros', async response => {
    await expect(readCompleteRecords('Test', async () => response)).rejects.toThrow('temporarily unavailable')
  })
  it('rejects a changing set between pages', async () => {
    const read = vi.fn().mockResolvedValueOnce({ data: [{ id: 'a' }], count: 2, error: null })
      .mockResolvedValueOnce({ data: [{ id: 'b' }], count: 3, error: null })
    await expect(readCompleteRecords('Test', read)).rejects.toThrow()
  })
  it('accepts a confirmed empty set', async () => {
    expect(await readCompleteRecords('Test', async () => ({ data: [], count: 0, error: null }))).toEqual([])
  })
  it('refuses oversized pages even when every identity is unique and the total count agrees', async () => {
    const read = vi.fn(async () => ({ data: Array.from({ length: 501 }, (_, i) => ({ id: String(i) })), count: 501, error: null }))
    await expect(readCompleteRecords('Test', read)).rejects.toThrow('temporarily unavailable')
    expect(read).toHaveBeenCalledTimes(1)
    expect(read).toHaveBeenCalledWith(0, 499)
  })
  it('allows an explicitly bounded topic cohort above the default ten thousand rows', async () => {
    const count = 11_495
    const read = vi.fn(async (from: number, to: number) => ({
      data: Array.from({ length: Math.min(to + 1, count) - from }, (_, index) => ({ id: String(from + index) })), count, error: null,
    }))
    expect(await readCompleteRecords('Topics', read, { maxRows: 20_000, maxPages: 40 })).toHaveLength(count)
    expect(read).toHaveBeenCalledTimes(23)
    expect(read).toHaveBeenLastCalledWith(11_000, 11_499)
  })
  it('enforces explicit row and page limits and never requests beyond the row budget', async () => {
    const read = vi.fn(async (from: number) => ({ data: [{ id: String(from) }], count: 3, error: null }))
    await expect(readCompleteRecords('Test', read, { maxRows: 3, maxPages: 2 })).rejects.toThrow('temporarily unavailable')
    expect(read.mock.calls.map(([from]) => from)).toEqual([0, 1])
    expect(read).toHaveBeenNthCalledWith(1, 0, 2)
    expect(read).toHaveBeenNthCalledWith(2, 1, 2)
    await expect(readCompleteRecords('Test', read, { maxRows: 2 })).rejects.toThrow('temporarily unavailable')
  })
  it.each([{ maxRows: 0 }, { maxRows: 50_001 }, { maxRows: 2.5 }, { maxRows: Number.NaN },
    { maxPages: 0 }, { maxPages: 101 }, { maxPages: Number.POSITIVE_INFINITY }, { maxPages: 1.5 }])
  ('rejects invalid explicit limits before any query: %j', async options => {
    const read = vi.fn(async () => ({ data: [], count: 0, error: null }))
    await expect(readCompleteRecords('Test', read, options)).rejects.toThrow('Invalid complete record read limits')
    expect(read).not.toHaveBeenCalled()
  })
})
