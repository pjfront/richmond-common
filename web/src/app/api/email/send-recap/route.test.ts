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
  sendRecapBroadcast: mocked.sendRecapBroadcast,
}))

import { POST } from './route'

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

describe('POST /api/email/send-recap legacy cutover', () => {
  afterEach(() => {
    vi.clearAllMocks()
    delete process.env.API_SECRET
  })

  it('refuses to replay a recap when either legacy marker is present', async () => {
    process.env.API_SECRET = 'test-secret'
    mocked.from.mockReturnValue(meetingQuery({
      id: 'meeting-1',
      meeting_date: '2026-08-01',
      meeting_type: 'regular',
      meeting_recap: 'Already delivered recap',
      meeting_recap_provenance: null,
      minutes_url: null,
      recap_emailed_at: null,
      transcript_recap_emailed_at: '2026-08-02T00:00:00.000Z',
    }))
    const request = {
      headers: new Headers({ authorization: 'Bearer test-secret' }),
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

  it('uses the transcript artifact and its matching provenance when minutes recap is absent', async () => {
    process.env.API_SECRET = 'test-secret'
    const transcriptProvenance = {
      kind: 'meeting_recording',
      channel: 'kcrt',
      as_of: '2026-08-01T23:00:00.000Z',
    }
    mocked.from.mockReturnValue(meetingQuery({
      id: 'meeting-2',
      city_fips: '0660620',
      meeting_date: '2026-08-01',
      meeting_type: 'regular',
      meeting_recap: null,
      meeting_recap_provenance: {
        kind: 'official_minutes',
        minutes_url: 'https://wrong.example/minutes.pdf',
        as_of: '2026-08-02T00:00:00.000Z',
      },
      transcript_recap: 'Transcript fallback recap',
      transcript_recap_provenance: transcriptProvenance,
      minutes_url: null,
      recap_emailed_at: null,
      transcript_recap_emailed_at: null,
      source_cancelled_at: null,
    }))
    mocked.sendRecapBroadcast.mockResolvedValue({
      sent: 1,
      failed: 0,
      already_sent: 0,
      deferred: 0,
      manual_review: 0,
      total_subscribers: 1,
      fully_delivered: true,
      emailed_at: '2026-08-02T01:00:00.000Z',
    })
    const request = {
      headers: new Headers({ authorization: 'Bearer test-secret' }),
      json: vi.fn(async () => ({ meeting_id: 'meeting-2' })),
    } as unknown as NextRequest

    const response = await POST(request)

    expect(response.status).toBe(200)
    expect(mocked.sendRecapBroadcast).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({
        meeting_recap: 'Transcript fallback recap',
        meeting_recap_provenance: transcriptProvenance,
        source: 'transcript',
      }),
    )
  })
})
