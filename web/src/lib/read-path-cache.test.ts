import { describe, expect, it } from 'vitest'
import {
  MAX_SIMILAR_ITEMS,
  OFFICIALS_CACHE_SECONDS,
  SIMILAR_ITEMS_CACHE_SECONDS,
  UPCOMING_ELECTION_CACHE_SECONDS,
} from './read-path-cache'

describe('read-path cache policy', () => {
  it('keeps the full officials read at a 24-hour TTL', () => {
    expect(OFFICIALS_CACHE_SECONDS).toBe(86_400)
  })

  it('keeps shared upcoming-election navigation data at a 24-hour TTL', () => {
    expect(UPCOMING_ELECTION_CACHE_SECONDS).toBe(86_400)
  })

  it('keeps similar discussions at the proposed bounded seven-day TTL', () => {
    expect(SIMILAR_ITEMS_CACHE_SECONDS).toBe(604_800)
    expect(MAX_SIMILAR_ITEMS).toBe(10)
  })
})
