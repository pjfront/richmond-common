import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import type { NextRequest } from 'next/server'

const mocked = vi.hoisted(() => ({
  searchHybrid: vi.fn(),
  searchSite: vi.fn(),
  getSupabaseAdmin: vi.fn(),
  rpc: vi.fn(),
  clientKey: vi.fn(),
  enforceRateLimit: vi.fn(),
}))

vi.mock('@/lib/queries', () => ({
  searchHybrid: mocked.searchHybrid,
  searchSite: mocked.searchSite,
}))

vi.mock('@/lib/supabase-admin', () => ({
  getSupabaseAdmin: mocked.getSupabaseAdmin,
}))

vi.mock('@/lib/rate-limit', () => ({
  clientKey: mocked.clientKey,
  enforceRateLimit: mocked.enforceRateLimit,
}))

import { GET } from './route'

function requestFor(query: string): NextRequest {
  const url = new URL('http://localhost/api/search')
  url.searchParams.set('q', query)
  return {
    headers: new Headers({ 'x-forwarded-for': '203.0.113.10' }),
    nextUrl: url,
  } as unknown as NextRequest
}

function embeddingResponse(
  totalTokens: unknown = 250,
  embedding: unknown = Array(1536).fill(0.125),
): Response {
  return Response.json({
    data: [{ embedding }],
    usage: { total_tokens: totalTokens },
  })
}

describe('GET /api/search paid embedding boundary', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    process.env.OPENAI_API_KEY = 'test-openai-key'
    delete process.env.RICHMOND_API_MONTHLY_CAP_USD
    delete process.env.RICHMOND_API_BUDGET_LOCK

    mocked.clientKey.mockReturnValue('203.0.113.10')
    mocked.enforceRateLimit.mockResolvedValue({
      allowed: true,
      backendAvailable: true,
    })
    mocked.searchSite.mockResolvedValue([])
    mocked.searchHybrid.mockResolvedValue([])
    mocked.getSupabaseAdmin.mockReturnValue({ rpc: mocked.rpc })
    mocked.rpc.mockImplementation(async (name: string) => {
      if (name === 'reserve_llm_cost') {
        return {
          data: [{ reserved: true, committed_cost: 0.001, reason: 'reserved' }],
          error: null,
        }
      }
      if (name === 'settle_llm_cost_reservation') {
        return { data: true, error: null }
      }
      throw new Error(`Unexpected RPC ${name}`)
    })

    fetchMock = vi.fn().mockResolvedValue(embeddingResponse())
    vi.stubGlobal('fetch', fetchMock)
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
  })

  afterEach(() => {
    delete process.env.OPENAI_API_KEY
    delete process.env.RICHMOND_API_MONTHLY_CAP_USD
    delete process.env.RICHMOND_API_BUDGET_LOCK
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    vi.clearAllMocks()
  })

  it('returns 429 only when the atomic per-IP counter reports exceeded', async () => {
    mocked.enforceRateLimit.mockResolvedValue({
      allowed: false,
      backendAvailable: true,
      response: Response.json({ error: 'Too many requests' }, { status: 429 }),
    })

    const response = await GET(requestFor('actual exceeded query'))

    expect(response.status).toBe(429)
    expect(mocked.rpc).not.toHaveBeenCalled()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(mocked.searchSite).not.toHaveBeenCalled()
  })

  it('falls back to keyword search when the rate-limit backend is unavailable', async () => {
    mocked.enforceRateLimit.mockResolvedValue({
      allowed: true,
      backendAvailable: false,
    })

    const response = await GET(requestFor('limiter unavailable query'))
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(body.results).toEqual([])
    expect(mocked.enforceRateLimit).toHaveBeenCalledWith('search', '203.0.113.10')
    expect(mocked.rpc).not.toHaveBeenCalled()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(mocked.searchSite).toHaveBeenCalledOnce()
    expect(mocked.searchHybrid).not.toHaveBeenCalled()
  })

  it('does not call OpenAI when the monthly reservation is refused', async () => {
    mocked.rpc.mockResolvedValueOnce({
      data: [{ reserved: false, committed_cost: 5, reason: 'monthly_cap_exceeded' }],
      error: null,
    })

    const response = await GET(requestFor('reservation refused query'))

    expect(response.status).toBe(200)
    expect(mocked.rpc).toHaveBeenCalledOnce()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(mocked.searchSite).toHaveBeenCalledOnce()
    expect(mocked.searchHybrid).not.toHaveBeenCalled()
  })

  it('honors the global budget lock before cache or reservation', async () => {
    const query = 'globally locked cached query'
    const primingResponse = await GET(requestFor(query))
    expect(primingResponse.status).toBe(200)
    expect(fetchMock).toHaveBeenCalledOnce()

    mocked.rpc.mockClear()
    fetchMock.mockClear()
    mocked.searchHybrid.mockClear()
    mocked.searchSite.mockClear()
    process.env.RICHMOND_API_BUDGET_LOCK = ' YeS '

    const response = await GET(requestFor(query))

    expect(response.status).toBe(200)
    expect(mocked.rpc).not.toHaveBeenCalled()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(mocked.searchSite).toHaveBeenCalledOnce()
    expect(mocked.searchHybrid).not.toHaveBeenCalled()
  })

  it('settles from provider usage at $0.02 per million tokens', async () => {
    const response = await GET(requestFor('successful metered query'))

    expect(response.status).toBe(200)
    expect(mocked.rpc).toHaveBeenNthCalledWith(
      1,
      'reserve_llm_cost',
      expect.objectContaining({
        p_model: 'text-embedding-3-small',
        p_monthly_cap: 5,
      }),
    )
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(mocked.rpc).toHaveBeenNthCalledWith(
      2,
      'settle_llm_cost_reservation',
      expect.objectContaining({
        p_actual_cost: 0.000005,
        p_input_tokens: 250,
        p_output_tokens: 0,
      }),
    )
    expect(mocked.searchHybrid).toHaveBeenCalledOnce()
    expect(mocked.searchSite).not.toHaveBeenCalled()
    expect(mocked.rpc.mock.invocationCallOrder[0]).toBeLessThan(
      fetchMock.mock.invocationCallOrder[0],
    )
    expect(fetchMock.mock.invocationCallOrder[0]).toBeLessThan(
      mocked.rpc.mock.invocationCallOrder[1],
    )
  })

  it('leaves the reservation open and falls back when usage is invalid', async () => {
    fetchMock.mockResolvedValueOnce(embeddingResponse('250'))

    const response = await GET(requestFor('invalid usage query'))

    expect(response.status).toBe(200)
    expect(mocked.rpc).toHaveBeenCalledOnce()
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(mocked.searchSite).toHaveBeenCalledOnce()
    expect(mocked.searchHybrid).not.toHaveBeenCalled()
  })

  it('falls back to keyword search when settlement cannot be proven', async () => {
    mocked.rpc
      .mockResolvedValueOnce({
        data: [{ reserved: true, committed_cost: 0.001, reason: 'reserved' }],
        error: null,
      })
      .mockResolvedValueOnce({ data: false, error: null })

    const response = await GET(requestFor('settlement failed query'))

    expect(response.status).toBe(200)
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(mocked.searchSite).toHaveBeenCalledOnce()
    expect(mocked.searchHybrid).not.toHaveBeenCalled()
  })

  it('accounts valid usage before rejecting a malformed vector', async () => {
    fetchMock.mockResolvedValueOnce(embeddingResponse(250, [0.125]))

    const response = await GET(requestFor('malformed vector query'))

    expect(response.status).toBe(200)
    expect(mocked.rpc).toHaveBeenCalledTimes(2)
    expect(mocked.rpc).toHaveBeenLastCalledWith(
      'settle_llm_cost_reservation',
      expect.objectContaining({ p_actual_cost: 0.000005, p_input_tokens: 250 }),
    )
    expect(mocked.searchSite).toHaveBeenCalledOnce()
    expect(mocked.searchHybrid).not.toHaveBeenCalled()
  })

  it('uses a normalized bounded cache only after rate authorization', async () => {
    const first = await GET(requestFor('Unique Cache Query'))
    const second = await GET(requestFor('  unique   cache query  '))

    expect(first.status).toBe(200)
    expect(second.status).toBe(200)
    expect(mocked.enforceRateLimit).toHaveBeenCalledTimes(2)
    expect(mocked.rpc).toHaveBeenCalledTimes(2)
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(mocked.searchHybrid).toHaveBeenCalledTimes(2)
  })
})
