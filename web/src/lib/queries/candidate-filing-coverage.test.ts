import { afterEach, describe, expect, it, vi } from 'vitest'
import inventory from './fixtures/anderson-filings-20260906.json'
import metadata from './fixtures/anderson-form460-217094857.json'
import { VERIFIED_ANDERSON_FILINGS } from '@/data/anderson-paper-filings'

const cached = vi.hoisted(() => ({ value: undefined as unknown }))
vi.mock('next/cache', () => ({ unstable_cache: (fn: () => Promise<unknown>) => async () => cached.value ?? await fn() }))
import { acquireAndersonFilingCoverage, getAndersonFilingCoverage } from './candidate-filing-coverage'

const now = new Date('2026-09-06T17:00:00Z')
const response = (value: unknown) => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } })
const fetcher = (list: unknown = inventory, info: unknown = metadata) => vi.fn<typeof fetch>()
  .mockResolvedValueOnce(response(list)).mockResolvedValueOnce(response(info))

describe('bounded official Anderson filing coverage', () => {
  afterEach(() => { cached.value = undefined; vi.unstubAllGlobals(); vi.useRealTimers() })

  it('uses the observed nonempty array despite totalCount=0, with exact identity and two bounded requests', async () => {
    const get = fetcher()
    const result = await acquireAndersonFilingCoverage(get, now)
    expect(inventory.totalCount).toBe(0)
    expect(inventory.filings).toHaveLength(22)
    expect(get).toHaveBeenCalledTimes(2)
    expect(get.mock.calls[0][0]).toBe('https://netfile.com/api/public/sites/api/filings/byFiler?agencyCode=RICH&filerId=214395297&isArchived=false')
    expect(get.mock.calls[1][0]).toBe('https://netfile.com/Connect2/api/public/filing/info/217094857?format=json')
    for (const [, options] of get.mock.calls) {
      expect(options?.signal).toBeInstanceOf(AbortSignal)
      expect(options?.redirect).toBe('error')
    }
    expect(result.checkedAt).toBe(now.toISOString())
    expect(result.latestPeriodic).toMatchObject({ id: '217094857', periodEnd: '2026-06-30', paperVerified: true })
    expect(result.recentRapid.map(filing => filing.id)).toEqual(['217352920', '217332630', '217243030', '217243444'])
    expect(JSON.stringify(result)).not.toContain('73300')
  })

  it.each([
    { sosFilerId: '1490887' }, { agency: 'OTHER' }, { amendedBy: 'replacement' },
    { dateEnd: '2026-05-30' }, { filingId: 'different' }, { isEfiled: undefined }, { formId: 'wrong-form' },
  ])('rejects identity, lineage, and period mismatches: %j', async changed => {
    await expect(acquireAndersonFilingCoverage(fetcher(inventory, { ...metadata, ...changed }), now)).rejects.toThrow('did not match')
  })

  it.each([
    { filings: [], totalCount: 0 }, { filings: inventory.filings, totalCount: 40 },
    { filings: Array(101).fill(inventory.filings[0]), totalCount: 0 },
    { filings: [...inventory.filings, inventory.filings[0]], totalCount: 0 },
  ])('never converts an empty, truncated, or repeated list to a complete-empty finding', async value => {
    await expect(acquireAndersonFilingCoverage(fetcher(value), now)).rejects.toThrow()
  })

  it('rejects a different committee rather than applying a surname alias', async () => {
    const changed = structuredClone(inventory)
    changed.filings[0].filerName = 'Safe Richmond Neighborhoods supporting Ahmad Anderson for Mayor 2026'
    await expect(acquireAndersonFilingCoverage(fetcher(changed), now)).rejects.toThrow('identity is ambiguous')
  })

  it('does not guess which same-period filing is the amendment', async () => {
    const latest = inventory.filings.find(filing => filing.id === '217094857')!
    const changed = { ...inventory, filings: [...inventory.filings, { ...latest, id: '999999999' }] }
    await expect(acquireAndersonFilingCoverage(fetcher(changed), now)).rejects.toThrow('missing or ambiguous')
  })

  it('lists a new rapid report without guessing that its PDF is paper or parsing its money', async () => {
    const changed = { ...inventory, filings: [{ ...inventory.filings[0], id: '999999998', filingDate: '2026-09-04T00:00:00+00:00' }, ...inventory.filings] }
    const result = await acquireAndersonFilingCoverage(fetcher(changed), now)
    expect(result.recentRapid).toHaveLength(4)
    expect(result.recentRapid[0]).toMatchObject({ id: '999999998', paperVerified: false, filedAt: '2026-09-04' })
  })

  it('includes reports filed after the periodic coverage end even before the periodic filing date', async () => {
    const latest = inventory.filings.find(filing => filing.id === '217094857')!
    const changed = { totalCount: 0, filings: [latest, { ...inventory.filings[0], id: '999999997', filingDate: '2026-07-15T00:00:00+00:00' }] }
    const result = await acquireAndersonFilingCoverage(fetcher(changed), now)
    expect(result.recentRapid.map(filing => filing.id)).toEqual(['999999997'])
  })

  it('bounds response bytes before JSON parsing', async () => {
    const get = vi.fn<typeof fetch>().mockResolvedValue(new Response(' '.repeat(256 * 1024 + 1)))
    await expect(acquireAndersonFilingCoverage(get, now)).rejects.toThrow('exceeds limit')
    expect(get).toHaveBeenCalledTimes(1)
  })

  it('keeps the dated verified fallback on a failed source check', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    const result = await getAndersonFilingCoverage()
    expect(result).toEqual({ ...VERIFIED_ANDERSON_FILINGS, status: 'unavailable' })
    expect(result.checkedAt).toBe('2026-09-06T16:45:39Z')
  })

  it('marks an older cached success as stale without replacing its verification time', async () => {
    cached.value = VERIFIED_ANDERSON_FILINGS
    vi.useFakeTimers().setSystemTime(new Date('2026-09-07T18:00:00Z'))
    expect(await getAndersonFilingCoverage()).toEqual({ ...VERIFIED_ANDERSON_FILINGS, status: 'stale' })
  })
})
