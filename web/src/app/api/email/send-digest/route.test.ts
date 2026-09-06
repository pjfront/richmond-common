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
import { broadcastTrackedEmail, loadActiveSubscribers } from '@/lib/email-delivery'

function request(body: Record<string, unknown> = {}, authorized = true) {
  return {
    headers: new Headers(authorized ? { authorization: 'Bearer test-secret' } : {}),
    json: vi.fn(async () => body),
  } as unknown as NextRequest
}

function digestMeetingQuery(rows: Record<string, unknown>[], error: unknown = null) {
  const result = { data: rows, error }
  const chain = {
    select: vi.fn(),
    in: vi.fn(),
    is: vi.fn(),
    not: vi.fn(),
    or: vi.fn(),
    eq: vi.fn(),
    gte: vi.fn(),
    lte: vi.fn(),
    order: vi.fn(),
    limit: vi.fn(),
    then: (resolve: (value: typeof result) => unknown) => Promise.resolve(resolve(result)),
  }
  chain.select.mockReturnValue(chain)
  chain.in.mockReturnValue(chain)
  chain.is.mockReturnValue(chain)
  chain.not.mockReturnValue(chain)
  chain.or.mockReturnValue(chain)
  chain.eq.mockReturnValue(chain)
  chain.gte.mockReturnValue(chain)
  chain.lte.mockReturnValue(chain)
  chain.order.mockReturnValue(chain)
  chain.limit.mockReturnValue(chain)
  return chain
}

describe('/api/email/send-digest canary and activated weekly delivery', () => {
  afterEach(() => {
    vi.clearAllMocks()
    vi.useRealTimers()
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
      broadcast_ready: true,
    })
    expect(JSON.stringify(body)).not.toContain('canary@example.test')
  })

  it('sends one provider-idempotent canary without loading subscribers', async () => {
    process.env.API_SECRET = 'test-secret'
    process.env.SUBSCRIBER_CANARY_EMAIL = 'canary@example.test'
    mocked.from.mockImplementation(table => table === 'civic_brief_candidates' ? digestMeetingQuery([]) : digestMeetingQuery([{
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
      { canary: true, briefs: [] },
    )
    expect(mocked.sendEmail).toHaveBeenCalledWith(expect.objectContaining({
      to: 'canary@example.test',
      idempotencyKey: expect.stringMatching(/^rc:digest:canary:week:/),
    }))
    expect(mocked.from.mock.calls.map(([table]) => table)).toEqual(['meetings', 'civic_brief_candidates'])
  })

  it('includes published updates in a brief-only canary without loading subscribers', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-07T12:00:00Z'))
    process.env.API_SECRET = 'test-secret'
    process.env.SUBSCRIBER_CANARY_EMAIL = 'canary@example.test'
    const brief = {
      id: '11111111-1111-4111-8111-111111111111', subject_key: '2026-general',
      title: 'An approved update', body: 'The official resolution advances two candidates.',
      sources: [{ url: 'https://www.richmondca.gov/Archive.aspx?ADID=17785', title: 'Official resolution', source_tier: 1 }],
      content_version: 2, published_at: '2026-09-01T12:00:00Z',
    }
    mocked.from.mockImplementation(table => digestMeetingQuery(table === 'civic_brief_candidates' ? [brief] : []))
    mocked.sendEmail.mockResolvedValue({ success: true, providerId: 'provider-brief' })

    const response = await POST(request({ mode: 'canary' }))

    expect(response.status).toBe(200)
    expect(mocked.buildDigestEmail).toHaveBeenCalledWith([], expect.stringContaining('/subscribe'), undefined, { canary: true, briefs: [brief] })
    expect(mocked.sendEmail).toHaveBeenCalledTimes(1)
    expect(mocked.from.mock.calls.map(([table]) => table)).toEqual(['meetings', 'civic_brief_candidates'])
  })

  it('surfaces an ambiguous provider result so the workflow forbids a rerun', async () => {
    process.env.API_SECRET = 'test-secret'
    process.env.SUBSCRIBER_CANARY_EMAIL = 'canary@example.test'
    mocked.from.mockImplementation(table => table === 'civic_brief_candidates' ? digestMeetingQuery([]) : digestMeetingQuery([{
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

  it.each(['broadcast', 'canary'])('requires authentication for %s before any query or delivery', async (mode) => {
    process.env.API_SECRET = 'test-secret'

    const response = await POST(request({ mode }, false))

    expect(response.status).toBe(401)
    expect(mocked.from).not.toHaveBeenCalled()
    expect(mocked.sendEmail).not.toHaveBeenCalled()
    expect(loadActiveSubscribers).not.toHaveBeenCalled()
    expect(broadcastTrackedEmail).not.toHaveBeenCalled()
  })

  it('sends nothing and does not load subscribers when the completed week has no eligible content', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-07T16:30:00Z'))
    process.env.API_SECRET = 'test-secret'
    mocked.from.mockReturnValue(digestMeetingQuery([]))

    const response = await POST(request({ mode: 'broadcast' }))

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual({
      mode: 'broadcast', sent: 0,
      period: { start: '2026-08-31', end: '2026-09-06', contentKey: 'week:2026-08-31' },
      reason: 'no recaps or reviewed updates in completed week',
    })
    expect(loadActiveSubscribers).not.toHaveBeenCalled()
    expect(broadcastTrackedEmail).not.toHaveBeenCalled()
    expect(mocked.sendEmail).not.toHaveBeenCalled()
  })

  it('fails source loading before subscriber selection or delivery rather than treating it as an empty week', async () => {
    process.env.API_SECRET = 'test-secret'
    mocked.from.mockImplementation(table => digestMeetingQuery([], table === 'civic_brief_candidates' ? { code: 'timeout' } : null))

    const response = await POST(request({ mode: 'broadcast' }))

    expect(response.status).toBe(503)
    expect(loadActiveSubscribers).not.toHaveBeenCalled()
    expect(broadcastTrackedEmail).not.toHaveBeenCalled()
    expect(mocked.sendEmail).not.toHaveBeenCalled()
  })

  it('identifies a broadcast with no active subscribers without attempting delivery', async () => {
    process.env.API_SECRET = 'test-secret'
    mocked.from.mockImplementation(table => digestMeetingQuery(table === 'meetings' ? [{
      id: '44444444-4444-4444-8444-444444444444', meeting_date: '2026-09-01',
      meeting_type: 'regular', meeting_recap: 'A persisted council recap.',
      meeting_recap_provenance: null, minutes_url: null,
    }] : []))
    vi.mocked(loadActiveSubscribers).mockResolvedValue([])

    const response = await POST(request({ mode: 'broadcast' }))

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual(expect.objectContaining({ mode: 'broadcast', sent: 0, reason: 'no active subscribers' }))
    expect(broadcastTrackedEmail).not.toHaveBeenCalled()
    expect(mocked.sendEmail).not.toHaveBeenCalled()
  })

  it('routes only a matching subject follow through tracked delivery with exact publication versions', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-07T16:30:00Z'))
    process.env.API_SECRET = 'test-secret'
    const followed = { id: '11111111-1111-4111-8111-111111111111', email: 'followed@example.test', unsubscribe_token: 'private-followed', receive_council_updates: false }
    const unrelated = { id: '22222222-2222-4222-8222-222222222222', email: 'unrelated@example.test', unsubscribe_token: 'private-unrelated', receive_council_updates: false }
    const brief = {
      id: '33333333-3333-4333-8333-333333333333', subject_key: '2026-general',
      title: 'A published election update', body: 'This is the exact source-checked publication.',
      sources: [{ url: 'https://www.richmondca.gov/Archive.aspx?ADID=17785', title: 'Official resolution', source_tier: 1, source_date: '2026-07-21' }],
      content_version: 2, published_at: '2026-09-06T12:00:00.123456+00:00',
    }
    const preferences = [
      { subscriber_id: followed.id, preference_type: 'subject', preference_value: '2026-general' },
      { subscriber_id: unrelated.id, preference_type: 'subject', preference_value: 'fire-stations-and-emergency-response' },
    ]
    mocked.from.mockImplementation(table => digestMeetingQuery(
      table === 'civic_brief_candidates' ? [brief] : table === 'email_preferences' ? preferences : [],
    ))
    vi.mocked(loadActiveSubscribers).mockResolvedValue([followed, unrelated])
    vi.mocked(broadcastTrackedEmail).mockResolvedValue({ sent: 1, failed: 0, already_sent: 0, deferred: 0, manual_review: 0, total_subscribers: 1, fully_delivered: true })

    const response = await POST(request({ mode: 'broadcast' }))

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toEqual(expect.objectContaining({ mode: 'broadcast', sent: 1, reviewed_update_count: 1, preference_filtered_out: 1 }))
    expect(broadcastTrackedEmail).toHaveBeenCalledTimes(1)
    const delivery = vi.mocked(broadcastTrackedEmail).mock.calls[0][0]
    expect(delivery).toEqual(expect.objectContaining({ kind: 'digest', contentKey: 'week:2026-08-31', subscribers: [followed] }))
    expect(delivery.briefVersions?.(followed)).toEqual([{ id: brief.id, content_version: 2, published_at: brief.published_at }])
    expect(delivery.containsCouncilContent?.(followed)).toBe(false)
    await delivery.build(followed, { unsubscribeUrl: '/unsubscribe/private', manageUrl: '/manage/private' })
    expect(mocked.buildDigestEmail).toHaveBeenCalledWith([], '/unsubscribe/private', '/manage/private', { briefs: [brief] })
    expect(mocked.sendEmail).not.toHaveBeenCalled()
  })
})
