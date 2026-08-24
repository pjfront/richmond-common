import { afterEach, describe, expect, it, vi } from 'vitest'
import type { NextRequest } from 'next/server'

const mocked = vi.hoisted(() => ({
  from: vi.fn(),
  sendRecapBroadcast: vi.fn(),
}))

vi.mock('@/lib/supabase-admin', () => ({
  getSupabaseAdmin: () => ({ from: mocked.from }),
}))
vi.mock('@/lib/email-delivery', () => ({
  MAX_BROADCAST_RECIPIENTS: 500,
  activationScopedContentKey: vi.fn((kind: string, contentKey: string, activationId?: string | null) =>
    kind === 'welcome' || !activationId
      ? contentKey
      : `${contentKey}:activation:${activationId}`,
  ),
  ensureBoundedRecipients: vi.fn((rows: unknown[]) => {
    if (rows.length > 500) throw new Error('Recipient safety cap exceeded')
    return rows
  }),
  sendRecapBroadcast: mocked.sendRecapBroadcast,
}))
vi.mock('@/lib/email', () => ({
  sendEmail: vi.fn(),
  buildRecapEmail: vi.fn(),
  buildOrientationEmail: vi.fn(),
}))
vi.mock('@/lib/operator-auth', () => ({
  withOperatorAuth: (handler: unknown) => handler,
}))
vi.mock('@/lib/logger', () => ({
  logEvent: vi.fn(),
  requestContext: vi.fn(() => ({})),
}))

import { GET, POST } from './route'

const MEETING_ID = '22222222-2222-4222-8222-222222222222'
const ACTIVATION_ID = '11111111-1111-4111-8111-111111111111'

function meetingQuery(meeting: Record<string, unknown>) {
  const chain = {
    select: vi.fn(),
    eq: vi.fn(),
    single: vi.fn(async () => ({ data: meeting, error: null })),
  }
  chain.select.mockReturnValue(chain)
  chain.eq.mockReturnValue(chain)
  return chain
}

function listQuery(data: unknown[], error: { message: string } | null = null) {
  const chain = {
    select: vi.fn(),
    eq: vi.fn(),
    in: vi.fn(),
    order: vi.fn(),
    limit: vi.fn(async () => ({ data, error })),
  }
  chain.select.mockReturnValue(chain)
  chain.eq.mockReturnValue(chain)
  chain.in.mockReturnValueOnce(chain).mockResolvedValueOnce({ data, error })
  chain.order.mockReturnValue(chain)
  return chain
}

function previewMeeting(overrides: Record<string, unknown> = {}) {
  return {
    id: MEETING_ID,
    meeting_date: '2026-08-01',
    meeting_type: 'regular',
    meeting_recap: null,
    meeting_recap_provenance: null,
    transcript_recap: null,
    transcript_recap_provenance: null,
    minutes_url: null,
    recap_emailed_at: null,
    transcript_recap_emailed_at: null,
    orientation_preview: null,
    orientation_preview_provenance: null,
    orientation_emailed_at: null,
    agenda_url: null,
    ...overrides,
  }
}

describe('GET /api/operator/send-recap delivery status', () => {
  afterEach(() => vi.clearAllMocks())

  it('counts only delivery identities from each active subscription cycle', async () => {
    const subscriberQuery = listQuery([
      { id: 'subscriber-1', current_activation_id: ACTIVATION_ID },
      { id: 'subscriber-2', current_activation_id: null },
    ])
    const deliveryQuery = listQuery([
      {
        subscriber_id: 'subscriber-1',
        status: 'sent',
        content_key: `meeting:${MEETING_ID}:activation:${ACTIVATION_ID}`,
      },
      {
        subscriber_id: 'subscriber-1',
        status: 'manual_review',
        content_key: `meeting:${MEETING_ID}:activation:33333333-3333-4333-8333-333333333333`,
      },
      {
        subscriber_id: 'subscriber-2',
        status: 'manual_review',
        content_key: `meeting:${MEETING_ID}`,
      },
    ])
    mocked.from.mockImplementation((table: string) => {
      if (table === 'meetings') return meetingQuery(previewMeeting())
      if (table === 'email_subscribers') return subscriberQuery
      if (table === 'email_deliveries') return deliveryQuery
      throw new Error(`Unexpected table: ${table}`)
    })
    const request = {
      nextUrl: new URL(`https://richmondcommons.org/api/operator/send-recap?meeting_id=${MEETING_ID}`),
    } as unknown as NextRequest

    const response = await GET(request)
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(body).toEqual(expect.objectContaining({
      subscriber_count: 2,
      delivered_count: 1,
      failed_count: 1,
      pending_count: 0,
    }))
    expect(deliveryQuery.in).toHaveBeenNthCalledWith(1, 'content_key', [
      `meeting:${MEETING_ID}:activation:${ACTIVATION_ID}`,
      `meeting:${MEETING_ID}`,
    ])
    expect(deliveryQuery.in).toHaveBeenNthCalledWith(2, 'subscriber_id', [
      'subscriber-1',
      'subscriber-2',
    ])
  })

  it('rejects malformed meeting ids before querying the database', async () => {
    const request = {
      nextUrl: new URL('https://richmondcommons.org/api/operator/send-recap?meeting_id=not-a-uuid'),
    } as unknown as NextRequest

    const response = await GET(request)

    expect(response.status).toBe(400)
    expect(mocked.from).not.toHaveBeenCalled()
  })
})

describe('POST /api/operator/send-recap legacy cutover', () => {
  afterEach(() => vi.clearAllMocks())

  it('refuses to replay a transcript recap recorded by a legacy marker', async () => {
    mocked.from.mockReturnValue(meetingQuery({
      id: 'meeting-1',
      meeting_date: '2026-08-01',
      meeting_type: 'regular',
      meeting_recap: null,
      meeting_recap_provenance: null,
      transcript_recap: 'Already delivered transcript recap',
      transcript_recap_provenance: null,
      minutes_url: null,
      recap_emailed_at: '2026-08-02T00:00:00.000Z',
      transcript_recap_emailed_at: null,
      orientation_preview: null,
      orientation_preview_provenance: null,
      agenda_url: null,
    }))
    const request = {
      headers: new Headers(),
      json: vi.fn(async () => ({ meeting_id: 'meeting-1' })),
    } as unknown as NextRequest

    const response = await POST(request)
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(body).toEqual(expect.objectContaining({
      sent: 0,
      already_sent: true,
      legacy_already_sent: true,
    }))
    expect(mocked.sendRecapBroadcast).not.toHaveBeenCalled()
  })
})
