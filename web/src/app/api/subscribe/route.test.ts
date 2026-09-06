import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { NextRequest } from 'next/server'
const mocked = vi.hoisted(() => ({ from: vi.fn(), rpc: vi.fn(), deliver: vi.fn(), limit: vi.fn() }))
vi.mock('@/lib/supabase-admin', () => ({ getSupabaseAdmin: () => ({ from: mocked.from, rpc: mocked.rpc }) }))
vi.mock('@/lib/email-delivery', () => ({ deliverTrackedEmail: mocked.deliver, welcomeContentKey: (id: string) => `welcome:${id}` }))
vi.mock('@/lib/email', () => ({ buildWelcomeEmail: vi.fn(), buildOrientationEmail: vi.fn() }))
vi.mock('@/lib/rate-limit', () => ({ clientKey: () => 'test', enforceRateLimit: mocked.limit }))
vi.mock('@/lib/logger', () => ({ emailHash: async () => 'hash', logEvent: vi.fn(), requestContext: () => ({}) }))
import { POST } from './route'

const activation = { activated: true, subscriber_id: 'subscriber', subscriber_name: 'Resident', unsubscribe_token: 'rotated-secret', activation_id: '11111111-1111-4111-8111-111111111111', receive_council_updates: false }
const success = { success: true, message: 'If this address can receive Richmond Commons updates, check the inbox for next steps.' }
function request(body: object) { return { json: async () => body, headers: new Headers() } as NextRequest }
function orientationQuery(data: unknown = null) {
  const query: Record<string, ReturnType<typeof vi.fn>> = {}
  for (const name of ['select', 'eq', 'gte', 'is', 'not', 'order', 'limit', 'update']) query[name] = vi.fn(() => query)
  query.maybeSingle = vi.fn(async () => ({ data, error: null }))
  return query
}

describe('subscription activation and consent boundary', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    mocked.limit.mockResolvedValue({ allowed: true })
    mocked.rpc.mockResolvedValue({ data: activation, error: null })
    mocked.deliver.mockResolvedValue({ status: 'sent', subscriberId: 'subscriber' })
  })
  afterEach(() => { vi.restoreAllMocks() })

  it('saves a whitelisted follow in the activation transaction and does not send an unrelated orientation', async () => {
    const response = await POST(request({ email: ' Resident@Example.Test ', follow: '2026-general', surface: 'november_election' }))
    expect(response.status).toBe(202)
    expect(await response.json()).toEqual(success)
    expect(mocked.rpc).toHaveBeenCalledExactlyOnceWith('activate_email_subscription_v2', {
      p_email: 'resident@example.test', p_name: null, p_surface: 'november_election', p_subject: '2026-general',
    })
    expect(mocked.from).not.toHaveBeenCalled()
    expect(mocked.deliver).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ kind: 'welcome', contentKey: `welcome:${activation.activation_id}`, subscriber: expect.objectContaining({ unsubscribe_token: 'rotated-secret' }) }))
  })

  it('preserves general signup onboarding using the atomically returned activation and rotated token', async () => {
    mocked.rpc.mockResolvedValue({ data: { ...activation, receive_council_updates: true }, error: null })
    const query = orientationQuery({ id: 'meeting', meeting_date: '2999-01-01', orientation_preview: 'A current council agenda.', orientation_preview_provenance: null, agenda_url: null })
    mocked.from.mockReturnValue(query)
    const response = await POST(request({ email: 'resident@example.test', surface: 'raw/untrusted/url' }))
    expect(await response.json()).toEqual(success)
    expect(mocked.rpc).toHaveBeenCalledWith('activate_email_subscription_v2', expect.objectContaining({ p_subject: null, p_surface: 'subscribe_page' }))
    expect(mocked.deliver).toHaveBeenNthCalledWith(2, expect.objectContaining({ kind: 'orientation', subscriber: expect.objectContaining({ current_activation_id: activation.activation_id, unsubscribe_token: activation.unsubscribe_token }) }))
    expect(query.eq).toHaveBeenCalledWith('bodies.body_type', 'city_council')
  })

  it.each(['already active', 'concurrent initial signup', 'concurrent reactivation'])('keeps %s generic and cannot change preferences or send onboarding', async () => {
    mocked.rpc.mockResolvedValue({ data: { activated: false }, error: null })
    const response = await POST(request({ email: 'resident@example.test', follow: '2026-general' }))
    expect(await response.json()).toEqual(success)
    expect(mocked.deliver).not.toHaveBeenCalled()
    expect(mocked.from).not.toHaveBeenCalled()
  })

  it.each(['other-city', '', ['2026-general'], { subject: '2026-general' }])('rejects an invalid follow without activating: %s', async follow => {
    expect((await POST(request({ email: 'resident@example.test', follow }))).status).toBe(400)
    expect(mocked.rpc).not.toHaveBeenCalled()
  })

  it('does not claim success or send mail if the atomic database write fails', async () => {
    mocked.rpc.mockResolvedValue({ data: null, error: { message: 'transaction rolled back' } })
    expect((await POST(request({ email: 'resident@example.test', follow: '2026-general' }))).status).toBe(500)
    expect(mocked.deliver).not.toHaveBeenCalled()
  })

  it.each(['provider rejection', 'unexpected exception'])('keeps successful activation private despite a %s', async failure => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    if (failure === 'unexpected exception') mocked.deliver.mockRejectedValueOnce(new Error('transport error'))
    else mocked.deliver.mockResolvedValueOnce({ status: 'failed', subscriberId: 'subscriber', error: 'provider rejected', retryable: true })
    const response = await POST(request({ email: 'resident@example.test', follow: '2026-general' }))
    expect(await response.json()).toEqual(success)
  })
})
