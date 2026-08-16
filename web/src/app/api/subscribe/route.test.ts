import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { NextRequest } from 'next/server'

const mocked = vi.hoisted(() => ({
  from: vi.fn(),
  deliverTrackedEmail: vi.fn(),
  enforceRateLimit: vi.fn(),
}))

vi.mock('@/lib/supabase-admin', () => ({
  getSupabaseAdmin: () => ({ from: mocked.from }),
}))

vi.mock('@/lib/email-delivery', () => ({
  deliverTrackedEmail: mocked.deliverTrackedEmail,
  welcomeContentKey: (activationId: string) => `welcome:${activationId}`,
}))

vi.mock('@/lib/email', () => ({
  buildWelcomeEmail: vi.fn(),
  buildOrientationEmail: vi.fn(),
}))

vi.mock('@/lib/rate-limit', () => ({
  clientKey: vi.fn(() => 'test-client'),
  enforceRateLimit: mocked.enforceRateLimit,
}))

vi.mock('@/lib/logger', () => ({
  emailHash: vi.fn(async () => 'email-hash'),
  logEvent: vi.fn(),
  requestContext: vi.fn(() => ({})),
}))

import { POST } from './route'

function request(body: Record<string, unknown>): NextRequest {
  return {
    json: vi.fn(async () => body),
    headers: new Headers(),
  } as unknown as NextRequest
}

function query(result: { data: unknown; error: unknown } | null = null) {
  const chain: Record<string, ReturnType<typeof vi.fn>> = {}
  for (const method of [
    'select', 'eq', 'update', 'insert', 'gte', 'is', 'not', 'order', 'limit',
  ]) {
    chain[method] = vi.fn(() => chain)
  }
  chain.single = vi.fn(async () => result ?? { data: null, error: null })
  chain.maybeSingle = vi.fn(async () => result ?? { data: null, error: null })
  return chain
}

describe('POST /api/subscribe credential boundary', () => {
  beforeEach(() => {
    mocked.enforceRateLimit.mockResolvedValue({ allowed: true, backendAvailable: true })
    mocked.deliverTrackedEmail.mockResolvedValue({ status: 'sent', subscriberId: 'subscriber-1' })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('reactivates as a new welcome cycle without disclosing the manage token', async () => {
    const reactivationQuery = query({
      data: {
        id: 'subscriber-1',
        subscribed_at: '2026-08-15T20:00:00.000Z',
        unsubscribe_token: 'durable-secret',
      },
      error: null,
    })
    mocked.from
      .mockReturnValueOnce(query({
        data: {
          id: 'subscriber-1',
          name: 'Existing name',
          status: 'unsubscribed',
          subscribed_at: '2026-01-01T00:00:00.000Z',
          unsubscribe_token: 'durable-secret',
        },
        error: null,
      }))
      .mockReturnValueOnce(reactivationQuery)
      .mockReturnValueOnce(query())

    const response = await POST(request({
      email: 'resident@example.test',
      surface: 'november_election',
    }))
    const body = await response.json()

    expect(response.status).toBe(201)
    expect(body).not.toHaveProperty('token')
    const activationWrite = reactivationQuery.update.mock.calls[0][0]
    expect(mocked.deliverTrackedEmail).toHaveBeenCalledWith(expect.objectContaining({
      kind: 'welcome',
      contentKey: `welcome:${activationWrite.current_activation_id}`,
    }))
    expect(reactivationQuery.update).toHaveBeenCalledWith(expect.objectContaining({
      status: 'active',
      subscribed_at: expect.any(String),
      current_activation_id: expect.stringMatching(/^[0-9a-f-]{36}$/),
      current_activation_at: expect.any(String),
      current_activation_surface: 'november_election',
    }))
    expect(activationWrite.current_activation_at).toBe(activationWrite.subscribed_at)
    expect(activationWrite).not.toHaveProperty('metadata')
  })

  it('does not disclose a newly created subscriber token either', async () => {
    const insertQuery = query({
      data: {
        id: 'subscriber-new',
        unsubscribe_token: 'new-durable-secret',
      },
      error: null,
    })
    mocked.from
      .mockReturnValueOnce(query())
      .mockReturnValueOnce(insertQuery)
      .mockReturnValueOnce(query())

    const response = await POST(request({ email: 'new@example.test' }))
    const body = await response.json()

    expect(response.status).toBe(201)
    expect(body).not.toHaveProperty('token')
    expect(insertQuery.insert).toHaveBeenCalledWith(expect.objectContaining({
      subscribed_at: expect.any(String),
      current_activation_id: expect.stringMatching(/^[0-9a-f-]{36}$/),
      current_activation_at: expect.any(String),
      current_activation_surface: 'subscribe_page',
    }))
    expect(insertQuery.insert.mock.calls[0][0]).not.toHaveProperty('metadata')
  })

  it('keeps signup successful but reports a retryable welcome delay honestly', async () => {
    mocked.deliverTrackedEmail.mockResolvedValueOnce({
      status: 'failed',
      subscriberId: 'subscriber-new',
      retryable: true,
      error: 'temporary failure',
    })
    mocked.from
      .mockReturnValueOnce(query())
      .mockReturnValueOnce(query({
        data: {
          id: 'subscriber-new',
          subscribed_at: '2026-08-15T21:00:00.000Z',
          unsubscribe_token: 'new-durable-secret',
        },
        error: null,
      }))
      .mockReturnValueOnce(query())

    const response = await POST(request({ email: 'new@example.test' }))
    const body = await response.json()

    expect(response.status).toBe(201)
    expect(body.message).toContain('delayed')
    expect(body.message).toContain('retry')
  })

  it('keeps the subscription truth when an unexpected welcome exception escapes', async () => {
    mocked.deliverTrackedEmail.mockRejectedValueOnce(new Error('network client threw'))
    mocked.from
      .mockReturnValueOnce(query())
      .mockReturnValueOnce(query({
        data: {
          id: 'subscriber-new',
          subscribed_at: '2026-08-15T21:00:00.000Z',
          unsubscribe_token: 'new-durable-secret',
        },
        error: null,
      }))
      .mockReturnValueOnce(query())

    const response = await POST(request({ email: 'new@example.test' }))
    const body = await response.json()

    expect(response.status).toBe(201)
    expect(body.message).toContain('subscription is still active')
    expect(body).not.toHaveProperty('token')
  })

  it('keeps an already-active duplicate out of new-acquisition delivery', async () => {
    mocked.from.mockReturnValueOnce(query({
      data: {
        id: 'subscriber-active',
        name: null,
        status: 'active',
        subscribed_at: '2026-08-15T21:00:00.000Z',
        unsubscribe_token: 'durable-secret',
        metadata: { acquisition_surface: 'homepage' },
      },
      error: null,
    }))

    const response = await POST(request({
      email: 'active@example.test',
      surface: 'november_election',
    }))
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(body.already_subscribed).toBe(true)
    expect(body).not.toHaveProperty('token')
    expect(mocked.deliverTrackedEmail).not.toHaveBeenCalled()
    expect(mocked.from).toHaveBeenCalledTimes(1)
  })
})
