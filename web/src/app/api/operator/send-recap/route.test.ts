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
