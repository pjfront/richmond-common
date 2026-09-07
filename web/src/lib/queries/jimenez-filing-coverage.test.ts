import { afterEach, describe, expect, it, vi } from 'vitest'
import inventory from './fixtures/jimenez-filings-20260906.json'
import metadata from './fixtures/jimenez-form460-217136864.json'
import { VERIFIED_JIMENEZ_FILINGS, hasNewJimenezReports, jimenezPeriodTotal } from '@/lib/jimenez-finance'

const cached = vi.hoisted(() => ({ values: new Map<string, unknown>(), keys: [] as string[] }))
vi.mock('next/cache', () => ({ unstable_cache: (fn: () => Promise<unknown>, keys: string[]) => {
  cached.keys.push(keys[0])
  return async () => cached.values.get(keys[0]) ?? await fn()
} }))
import { acquireJimenezFilingCoverage, getJimenezFilingCoverage } from './candidate-filing-coverage'

const now = new Date('2026-09-06T22:00:00Z')
const response = (value: unknown) => new Response(JSON.stringify(value))
const fetcher = (list: unknown = inventory, info: unknown = metadata) => vi.fn<typeof fetch>()
  .mockResolvedValueOnce(response(list)).mockResolvedValueOnce(response(info))

describe('bounded official Jimenez filing freshness', () => {
  afterEach(() => { cached.values.clear(); vi.unstubAllGlobals(); vi.useRealTimers() })

  it('checks the actual30-row inventory and exact electronic460 with two bounded requests', async () => {
    const get = fetcher()
    const coverage = await acquireJimenezFilingCoverage(get, now)
    expect(inventory.filings).toHaveLength(30)
    expect(inventory.totalCount).toBe(0)
    expect(get).toHaveBeenCalledTimes(2)
    expect(get.mock.calls[0][0]).toBe('https://netfile.com/api/public/sites/api/filings/byFiler?agencyCode=RICH&filerId=215890728&isArchived=false')
    expect(get.mock.calls[1][0]).toBe('https://netfile.com/Connect2/api/public/filing/info/217136864?format=json')
    for (const [, options] of get.mock.calls) {
      expect(options?.redirect).toBe('error')
      expect(options?.signal).toBeInstanceOf(AbortSignal)
    }
    expect(coverage.latestPeriodic).toMatchObject({ id: '217136864', periodStart: '2026-05-17', periodEnd: '2026-06-30', paperVerified: false })
    expect(coverage.recentRapid.map(row => row.id)).toEqual(['217270674', '217136812', '217136825', '217136849'])
    expect(hasNewJimenezReports(coverage)).toBe(false)
    expect(JSON.stringify(coverage)).not.toMatch(/60365|68918|donor|received_date/)
  })

  it('keeps irrelevant earlier410 names out of money identity matching, while refusing any different relevant filer', async () => {
    expect(inventory.filings.some(row => row.formName === 'FPPC 410' && row.filerName !== metadata.filerName)).toBe(true)
    const changed = structuredClone(inventory)
    changed.filings[0].filerName = 'Claudia Jimenez for District 6 Richmond City Council 2024'
    await expect(acquireJimenezFilingCoverage(fetcher(changed), now)).rejects.toThrow('identity is ambiguous')
  })

  it.each([
    { sosFilerId: '1467767' }, { agency: 'OTHER' }, { amendedBy: '217999999' },
    { filingId: 'wrong' }, { dateStart: '2026-05-29' }, { isEfiled: undefined }, { formId: 'different' },
  ])('rejects metadata identity and lineage mismatches: %j', async changed => {
    await expect(acquireJimenezFilingCoverage(fetcher(inventory, { ...metadata, ...changed }), now)).rejects.toThrow('did not match')
  })

  it('does not choose between an original and an amendment for the same latest period without resolving lineage', async () => {
    const latest = inventory.filings.find(row => row.id === '217136864')!
    const changed = { ...inventory, filings: [...inventory.filings,
      { ...latest, id: '999999998', formName: 'FPPC 460 (Amendment)', sequenceNumber: '1' }] }
    await expect(acquireJimenezFilingCoverage(fetcher(changed), now)).rejects.toThrow('missing or ambiguous')
  })

  it('recognizes a new rapid amendment as a review signal without interpreting money or receipt dates', async () => {
    const changed = { ...inventory, filings: [{ ...inventory.filings[0], id: '999999997',
      formName: 'FPPC Form 497 (Amendment)', filingDate: '2026-09-05T00:00:00+00:00' }, ...inventory.filings] }
    const coverage = await acquireJimenezFilingCoverage(fetcher(changed), now)
    expect(coverage.recentRapid[0]).toMatchObject({ id: '999999997', filedAt: '2026-09-05', paperVerified: false })
    expect(hasNewJimenezReports(coverage)).toBe(true)
    expect(jimenezPeriodTotal()).toBe(6_036_500)
  })

  it('preserves the report and original checked date after a failure, with independent cache identity', async () => {
    expect(cached.keys).toContain('candidate-paper-1481105-v1')
    expect(cached.keys).toContain('candidate-filings-1488504-v1')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('timeout')))
    expect(await getJimenezFilingCoverage()).toEqual({ ...VERIFIED_JIMENEZ_FILINGS, status: 'unavailable' })
  })

  it('labels an old cached success stale rather than replacing its check time', async () => {
    cached.values.set('candidate-filings-1488504-v1', VERIFIED_JIMENEZ_FILINGS)
    vi.useFakeTimers().setSystemTime(new Date('2026-09-07T22:00:00Z'))
    expect(await getJimenezFilingCoverage()).toEqual({ ...VERIFIED_JIMENEZ_FILINGS, status: 'stale' })
  })

  it.each([
    { filings: [], totalCount: 0 }, { filings: inventory.filings, totalCount: 999 },
    { filings: Array(101).fill(inventory.filings[0]), totalCount: 0 },
    { filings: [...inventory.filings, inventory.filings[0]], totalCount: 0 },
  ])('rejects empty, oversized, repeated or partial inventories', async list => {
    await expect(acquireJimenezFilingCoverage(fetcher(list), now)).rejects.toThrow()
  })

  it('enforces byte bounds without any PDF or retry request', async () => {
    const get = vi.fn<typeof fetch>().mockResolvedValue(new Response(' '.repeat(256 * 1024 + 1)))
    await expect(acquireJimenezFilingCoverage(get, now)).rejects.toThrow('exceeds limit')
    expect(get).toHaveBeenCalledTimes(1)
  })
})
