/**
 * Bucket-boundary safeguard for `contributionBuckets.ts`.
 *
 * The 5 amount buckets are tied to real California campaign-finance
 * rules verified in D56b (docs/AI-PARKING-LOT.md, 2026-05-17). Each
 * boundary represents a regulatory threshold:
 *
 *   $100   — FPPC itemization / disclosure of donor name+employer
 *   $250   — SB 1439 (Gov Code §84308) pay-to-play recusal trigger
 *   $1,000 — Form 497 24-hour late-contribution report trigger
 *   $2,500 — Richmond Municipal Code §2.42.050(a)(1) per-cycle cap
 *
 * If a future commit "rounds these nicely" (e.g., $1,000 → $1,500), this
 * test fails and forces the editor to update both the parking-lot entry
 * and the methodology page. The boundaries shouldn't change unless the
 * underlying rules change.
 */
import { describe, it, expect } from 'vitest'
import {
  BUCKETS,
  SOURCE_TYPES,
  bucketKeyForAmount,
  classifyContributorType,
  emptyMatrix,
  addToMatrix,
} from './contributionBuckets'

describe('BUCKETS', () => {
  it('has exactly 5 buckets keyed on California regulatory thresholds', () => {
    expect(BUCKETS).toHaveLength(5)
  })

  it('boundaries match D56b verified anchors', () => {
    // Each tuple is [bucket key, min, max]. Maxes are half-open
    // (amount < max). 2500 has +Infinity max because Richmond caps any
    // single contribution at 2500 — anything at-or-above lands here.
    const expected: Array<[string, number, number]> = [
      ['under_100', 0, 100],
      ['between_100_249', 100, 250],
      ['between_250_999', 250, 1000],
      ['between_1000_2499', 1000, 2500],
      ['at_2500_cap', 2500, Number.POSITIVE_INFINITY],
    ]
    expect(BUCKETS.map((b) => [b.key, b.min, b.max])).toEqual(expected)
  })

  it('every bucket cites a primary source in its rationale', () => {
    for (const b of BUCKETS) {
      expect(b.source.length).toBeGreaterThan(0)
      expect(b.rationale.length).toBeGreaterThan(0)
    }
  })
})

describe('SOURCE_TYPES', () => {
  it('exposes 4 plain-language source types', () => {
    expect(SOURCE_TYPES.map((s) => s.key)).toEqual([
      'individual',
      'business',
      'union',
      'pac',
    ])
  })
})

describe('bucketKeyForAmount', () => {
  it.each([
    [50, 'under_100'],
    [99.99, 'under_100'],
    [100, 'between_100_249'],
    [249, 'between_100_249'],
    [250, 'between_250_999'],
    [999.99, 'between_250_999'],
    [1000, 'between_1000_2499'],
    [2499.99, 'between_1000_2499'],
    [2500, 'at_2500_cap'],
    [5000, 'at_2500_cap'],
  ])('amount %s falls in %s', (amount, expected) => {
    expect(bucketKeyForAmount(amount)).toBe(expected)
  })
})

describe('classifyContributorType', () => {
  it.each([
    ['individual', 'individual'],
    ['union', 'union'],
    ['pac_ie', 'pac'],
    ['corporate', 'business'],
    ['other', 'business'],     // 'other' folds into business per FPPC OTH convention
    [null, 'business'],         // unclassified rows are never silently dropped
    [undefined, 'business'],
  ])('raw %s maps to %s', (raw, expected) => {
    expect(classifyContributorType(raw as string | null | undefined)).toBe(expected)
  })
})

describe('emptyMatrix + addToMatrix', () => {
  it('initializes a dense 5x4 matrix with all-zero cells', () => {
    const m = emptyMatrix()
    expect(m.total_count).toBe(0)
    expect(m.total_dollars).toBe(0)
    for (const s of SOURCE_TYPES) {
      for (const b of BUCKETS) {
        const cell = m.cells[s.key][b.key]
        expect(cell.count).toBe(0)
        expect(cell.dollars).toBe(0)
      }
    }
  })

  it('routes individual + $150 to (individual, between_100_249)', () => {
    const m = emptyMatrix()
    addToMatrix(m, { amount: 150, contributor_type: 'individual' })
    expect(m.cells.individual.between_100_249).toEqual({ count: 1, dollars: 150 })
    expect(m.total_count).toBe(1)
    expect(m.total_dollars).toBe(150)
  })

  it('routes pac_ie + $2,500 to (pac, at_2500_cap) and aggregates', () => {
    const m = emptyMatrix()
    addToMatrix(m, { amount: 2500, contributor_type: 'pac_ie' })
    addToMatrix(m, { amount: 2500, contributor_type: 'pac_ie' })
    expect(m.cells.pac.at_2500_cap).toEqual({ count: 2, dollars: 5000 })
    expect(m.total_count).toBe(2)
    expect(m.total_dollars).toBe(5000)
  })

  it('reproduces the Jimenez D56b sample shape', () => {
    // Probe 7 from session: Jimenez has 5 union contribs ($11K), 1 PAC
    // at $2,500, and a mix of individual contribs (58 across 5 buckets).
    // We only test a few representative rows here — the full sample
    // lives in the live-DB query verification (RICHMOND_RUN_DB_TESTS=1).
    const rows = [
      { amount: 50, contributor_type: 'individual' },
      { amount: 100, contributor_type: 'individual' },
      { amount: 2500, contributor_type: 'union' },
      { amount: 2500, contributor_type: 'pac_ie' },
      { amount: 1000, contributor_type: 'union' },
    ]
    const m = emptyMatrix()
    for (const r of rows) addToMatrix(m, r)
    expect(m.total_count).toBe(5)
    expect(m.total_dollars).toBe(6150)
    expect(m.cells.individual.under_100.count).toBe(1)
    expect(m.cells.individual.between_100_249.count).toBe(1)
    expect(m.cells.union.at_2500_cap.count).toBe(1)
    expect(m.cells.union.between_1000_2499.count).toBe(1)
    expect(m.cells.pac.at_2500_cap.count).toBe(1)
  })
})
