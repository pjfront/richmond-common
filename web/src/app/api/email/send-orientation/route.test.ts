import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { NextRequest } from 'next/server'

const mocked = vi.hoisted(() => ({
  from: vi.fn(),
  loadActiveSubscribers: vi.fn(),
  broadcastTrackedEmail: vi.fn(),
  areAllDeliveriesSent: vi.fn(),
}))

vi.mock('@/lib/supabase-admin', () => ({
  getSupabaseAdmin: () => ({ from: mocked.from }),
}))

vi.mock('@/lib/email-delivery', () => ({
  loadActiveSubscribers: mocked.loadActiveSubscribers,
  broadcastTrackedEmail: mocked.broadcastTrackedEmail,
  areAllDeliveriesSent: mocked.areAllDeliveriesSent,
}))

vi.mock('@/lib/email', () => ({ buildOrientationEmail: vi.fn() }))

import { POST } from './route'

function request(body: Record<string, unknown>): NextRequest {
  return {
    headers: new Headers({ authorization: 'Bearer test-secret' }),
    json: vi.fn(async () => body),
  } as unknown as NextRequest
}

function meetingQuery(result: { data: unknown; error: unknown }) {
  const chain: Record<string, ReturnType<typeof vi.fn>> = {}
  for (const method of ['select', 'eq', 'gte', 'is', 'not', 'order']) {
    chain[method] = vi.fn(() => chain)
  }
  chain.limit = vi.fn(async () => result)
  chain.single = vi.fn(async () => result)
  return chain
}

describe('POST /api/email/send-orientation council scope', () => {
  beforeEach(() => {
    vi.stubEnv('API_SECRET', 'test-secret')
    mocked.loadActiveSubscribers.mockResolvedValue([])
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllEnvs()
    vi.clearAllMocks()
  })

  it('discovers only upcoming regular City Council meetings in Richmond time', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-25T00:30:00Z'))
    const query = meetingQuery({ data: [], error: null })
    mocked.from.mockReturnValue(query)

    const response = await POST(request({}))

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toMatchObject({
      sent: 0,
      reason: 'no orientation candidates',
    })
    expect(query.select).toHaveBeenCalledWith(
      expect.stringContaining('bodies!inner(body_type)'),
    )
    expect(query.eq).toHaveBeenCalledWith('city_fips', '0660620')
    expect(query.eq).toHaveBeenCalledWith('meeting_type', 'regular')
    expect(query.eq).toHaveBeenCalledWith('bodies.body_type', 'city_council')
    expect(query.gte).toHaveBeenCalledWith('meeting_date', '2026-08-24')
  })

  it('applies the same council boundary to an exact meeting request', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-25T00:30:00Z'))
    const query = meetingQuery({
      data: {
        id: '22222222-2222-4222-8222-222222222222',
        meeting_date: '2999-01-01',
        orientation_preview: 'A current agenda preview.',
        orientation_preview_provenance: null,
        agenda_url: null,
        orientation_emailed_at: null,
      },
      error: null,
    })
    mocked.from.mockReturnValue(query)

    const response = await POST(request({
      meeting_id: '22222222-2222-4222-8222-222222222222',
    }))

    expect(response.status).toBe(200)
    expect(query.eq).toHaveBeenCalledWith('city_fips', '0660620')
    expect(query.eq).toHaveBeenCalledWith('meeting_type', 'regular')
    expect(query.eq).toHaveBeenCalledWith('bodies.body_type', 'city_council')
    expect(query.gte).toHaveBeenCalledWith('meeting_date', '2026-08-24')
    expect(mocked.loadActiveSubscribers).toHaveBeenCalledOnce()
    expect(mocked.broadcastTrackedEmail).not.toHaveBeenCalled()
  })
})
