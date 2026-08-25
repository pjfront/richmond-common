import { describe, expect, it } from 'vitest'
import { richmondDateKey } from './richmond-date'

describe('richmondDateKey', () => {
  it.each([
    ['2026-08-25T06:59:59Z', '2026-08-24'],
    ['2026-08-25T07:00:00Z', '2026-08-25'],
    ['2026-12-01T07:59:59Z', '2026-11-30'],
    ['2026-12-01T08:00:00Z', '2026-12-01'],
  ])('maps %s to Richmond civil date %s', (instant, expected) => {
    expect(richmondDateKey(new Date(instant))).toBe(expected)
  })
})
