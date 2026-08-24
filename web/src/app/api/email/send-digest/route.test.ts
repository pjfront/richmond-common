import { afterEach, describe, expect, it, vi } from 'vitest'
import type { NextRequest } from 'next/server'

const mocked = vi.hoisted(() => ({
  from: vi.fn(),
  sendEmail: vi.fn(),
  buildDigestEmail: vi.fn(() => ({
    subject: '[CANARY] Weekly digest',
    html: '<p>Canary</p>',
    text: 'Canary',
  })),
}))

vi.mock('@/lib/supabase-admin', () => ({
  getSupabaseAdmin: () => ({ from: mocked.from }),
}))
vi.mock('@/lib/email', () => ({
  buildDigestEmail: mocked.buildDigestEmail,
  sendEmail: mocked.sendEmail,
}))
vi.mock('@/lib/email-delivery', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/lib/email-delivery')>()
  return {
    ...original,
    broadcastTrackedEmail: vi.fn(),
    loadActiveSubscribers: vi.fn(),
  }
})

import { GET, POST } from './route'

function request(body: Record<string, unknown> = {}) {
  return {
    headers: new Headers({ authorization: 'Bearer test-secret' }),
    json: vi.fn(async () => body),
  } as unknown as NextRequest
}

function digestMeetingQuery(rows: Record<string, unknown>[]) {
  const result = { data: rows, error: null }
  const chain = {
    select: vi.fn(),
    eq: vi.fn(),
    gte: vi.fn(),
    lte: vi.fn(),
    order: vi.fn(),
    limit: vi.fn(),
    then: (resolve: (value: typeof result) => unknown) => Promise.resolve(resolve(result)),
  }
  chain.select.mockReturnValue(chain)
  chain.eq.mockReturnValue(chain)
  chain.gte.mockReturnValue(chain)
  chain.lte.mockReturnValue(chain)
  chain.order.mockReturnValue(chain)
  chain.limit.mockReturnValue(chain)
  return chain
}

describe('/api/email/send-digest canary control', () => {
  afterEach(() => {
    vi.clearAllMocks()
    delete process.env.API_SECRET
    delete process.env.SUBSCRIBER_CANARY_EMAIL
  })

  it('reports capability without exposing the configured address', async () => {
    process.env.API_SECRET = 'test-secret'
    process.env.SUBSCRIBER_CANARY_EMAIL = 'canary@example.test'

    const response = await GET(request())
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(body).toEqual({
      capability: 'subscriber-weekly-digest-v1',
      canary_ready: true,
      broadcast_ready: false,
    })
    expect(JSON.stringify(body)).not.toContain('canary@example.test')
  })

  it('sends one provider-idempotent canary without loading subscribers', async () => {
    process.env.API_SECRET = 'test-secret'
    process.env.SUBSCRIBER_CANARY_EMAIL = 'canary@example.test'
    mocked.from.mockReturnValue(digestMeetingQuery([{
      id: '11111111-1111-4111-8111-111111111111',
      meeting_date: '2026-08-05',
      meeting_type: 'regular',
      meeting_recap: 'Council discussed an agenda item.',
      meeting_recap_provenance: null,
      minutes_url: null,
      recap_emailed_at: null,
      transcript_recap_emailed_at: null,
    }]))
    mocked.sendEmail.mockResolvedValue({ success: true, providerId: 'provider-1' })

    const response = await POST(request({ mode: 'canary' }))
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(body).toEqual(expect.objectContaining({
      mode: 'canary',
      sent: 1,
      provider_confirmed: true,
    }))
    expect(mocked.buildDigestEmail).toHaveBeenCalledWith(
      expect.any(Array),
      expect.stringContaining('/subscribe'),
      undefined,
      { canary: true },
    )
    expect(mocked.sendEmail).toHaveBeenCalledWith(expect.objectContaining({
      to: 'canary@example.test',
      idempotencyKey: expect.stringMatching(/^rc:digest:canary:week:/),
    }))
    expect(mocked.from).toHaveBeenCalledTimes(1)
  })

  it('surfaces an ambiguous provider result so the workflow forbids a rerun', async () => {
    process.env.API_SECRET = 'test-secret'
    process.env.SUBSCRIBER_CANARY_EMAIL = 'canary@example.test'
    mocked.from.mockReturnValue(digestMeetingQuery([{
      id: '33333333-3333-4333-8333-333333333333',
      meeting_date: '2026-08-05',
      meeting_type: 'regular',
      meeting_recap: 'Council discussed an agenda item.',
      meeting_recap_provenance: null,
      minutes_url: null,
      recap_emailed_at: null,
      transcript_recap_emailed_at: null,
    }]))
    mocked.sendEmail.mockResolvedValue({
      success: false,
      error: 'Email provider response was not confirmed',
      ambiguous: true,
    })

    const response = await POST(request({ mode: 'canary' }))
    const body = await response.json()

    expect(response.status).toBe(503)
    expect(body).toEqual(expect.objectContaining({
      mode: 'canary',
      sent: 0,
      provider_confirmed: false,
      ambiguous: true,
    }))
  })

  it('fails closed when canary configuration is absent', async () => {
    process.env.API_SECRET = 'test-secret'

    const response = await POST(request({ mode: 'canary' }))

    expect(response.status).toBe(503)
    expect(mocked.from).not.toHaveBeenCalled()
    expect(mocked.sendEmail).not.toHaveBeenCalled()
  })

  it.each([
    'two@example.test,other@example.test',
    'two@example.test;other@example.test',
    ' leading@example.test',
    'trailing@example.test ',
    'line@example.test\r\nBcc: other@example.test',
    'missing-at.example.test',
    'missing-domain@example',
    '<invalid>@example.test',
    '.leading-dot@example.test',
    'double..dot@example.test',
    'name@-invalid.example',
  ])('rejects an invalid or multiple canary recipient before querying: %s', async (value) => {
    process.env.API_SECRET = 'test-secret'
    process.env.SUBSCRIBER_CANARY_EMAIL = value

    const response = await POST(request({ mode: 'canary' }))

    expect(response.status).toBe(503)
    expect(mocked.from).not.toHaveBeenCalled()
    expect(mocked.sendEmail).not.toHaveBeenCalled()
  })

  it('refuses a missing mode before any query or delivery', async () => {
    process.env.API_SECRET = 'test-secret'

    const response = await POST(request())

    expect(response.status).toBe(400)
    expect(mocked.from).not.toHaveBeenCalled()
    expect(mocked.sendEmail).not.toHaveBeenCalled()
  })

  it('refuses broadcast in code before the post-canary activation release', async () => {
    process.env.API_SECRET = 'test-secret'

    const response = await POST(request({ mode: 'broadcast' }))

    expect(response.status).toBe(409)
    await expect(response.json()).resolves.toEqual({
      error: 'Subscriber digest broadcast is not activated',
    })
    expect(mocked.from).not.toHaveBeenCalled()
    expect(mocked.sendEmail).not.toHaveBeenCalled()
  })
})
