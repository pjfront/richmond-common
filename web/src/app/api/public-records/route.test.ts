import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ snapshot: vi.fn() }))
vi.mock('@/lib/queries/public_records', () => ({ getPublicRecordsSnapshot: mocks.snapshot }))
import { GET } from './route'
describe('public-record API failures', () => {
  beforeEach(() => { mocks.snapshot.mockReset(); vi.spyOn(console, 'error').mockImplementation(() => {}) })
  afterEach(() => vi.restoreAllMocks())
  it('returns noncacheable 503 instead of invented zeros on incomplete reads', async () => {
    mocks.snapshot.mockRejectedValue(new Error('private backend diagnostic'))
    const response = await GET()
    expect(response.status).toBe(503)
    expect(response.headers.get('Cache-Control')).toBe('no-store')
    expect(await response.text()).not.toContain('private backend')
  })
  it('reads once and exposes only coherent observed summaries', async () => {
    const stats = { totalRequests: 2, closedRequests: 1, notClosedRequests: 1, closureTimingCount: 0, avgClosureDays: null }
    mocks.snapshot.mockResolvedValue({ stats, departments: [], requests: [{ private: 'not in API' }] })
    const response = await GET()
    expect(response.status).toBe(200)
    expect(await response.json()).toEqual({ stats, departments: [] })
    expect(mocks.snapshot).toHaveBeenCalledOnce()
  })
})
