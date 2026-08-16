import { afterEach, describe, expect, it, vi } from 'vitest'
import type { NextRequest } from 'next/server'

const mocked = vi.hoisted(() => ({
  retryPendingEmailDeliveries: vi.fn(),
}))

vi.mock('@/lib/supabase-admin', () => ({
  getSupabaseAdmin: () => ({ from: vi.fn(), rpc: vi.fn() }),
}))
vi.mock('@/lib/email-delivery', () => ({
  retryPendingEmailDeliveries: mocked.retryPendingEmailDeliveries,
}))

import { POST } from './route'

describe('POST /api/email/retry-deliveries', () => {
  afterEach(() => {
    vi.clearAllMocks()
    delete process.env.API_SECRET
  })

  it('surfaces a shared bounded backlog as workflow-detectable failure', async () => {
    process.env.API_SECRET = 'test-secret'
    mocked.retryPendingEmailDeliveries.mockResolvedValue({
      sent: 50,
      failed: 0,
      already_sent: 0,
      deferred: 0,
      manual_review: 0,
      total_subscribers: 50,
      fully_delivered: true,
      pending_rows: 50,
      stale_deliveries: 0,
      cancelled: 0,
      fully_resolved: false,
      backlog_remaining: true,
    })
    const request = {
      headers: new Headers({ authorization: 'Bearer test-secret' }),
    } as unknown as NextRequest

    const response = await POST(request)

    expect(response.status).toBe(503)
    expect(mocked.retryPendingEmailDeliveries).toHaveBeenCalledOnce()
  })

  it('rejects requests without the server secret', async () => {
    const request = { headers: new Headers() } as unknown as NextRequest

    const response = await POST(request)

    expect(response.status).toBe(401)
    expect(mocked.retryPendingEmailDeliveries).not.toHaveBeenCalled()
  })
})
