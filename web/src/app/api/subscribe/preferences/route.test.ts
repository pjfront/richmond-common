import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { NextRequest } from 'next/server'
const mocks = vi.hoisted(() => ({ from: vi.fn(), rpc: vi.fn() }))
vi.mock('@/lib/supabase-admin', () => ({ getSupabaseAdmin: () => mocks }))
vi.mock('@/lib/rate-limit', () => ({ clientKey: () => 'test', enforceRateLimit: async () => ({ allowed: true }) }))
import { PATCH } from './route'

const auth = { id: 'subscriber', status: 'active', name: null, receive_council_updates: false }
const saved = [{ preference_type: 'subject', preference_value: '2026-general' }]
function query(data: unknown) {
  const result = { data, error: null }
  const chain = { select: vi.fn(), eq: vi.fn(), single: async () => result, then: (resolve: (value: unknown) => unknown) => Promise.resolve(result).then(resolve) }
  chain.select.mockReturnValue(chain); chain.eq.mockReturnValue(chain)
  return chain
}
function request(preferences: object) { return { json: async () => ({ token: '11111111-1111-4111-8111-111111111111', preferences }) } as NextRequest }
describe('management-token subject preferences', () => {
  beforeEach(() => { vi.resetAllMocks(); mocks.from.mockReturnValueOnce(query(auth)).mockReturnValueOnce(query(saved)); mocks.rpc.mockResolvedValue({ error: null }) })
  it('saves subjects and council consent in one versioned authenticated replacement', async () => {
    const response = await PATCH(request({ topics: [], districts: [], candidates: [], subjects: ['2026-general'], receiveCouncilUpdates: false }))
    expect(response.status).toBe(200)
    expect(mocks.rpc).toHaveBeenCalledExactlyOnceWith('replace_email_preferences_v2', {
      p_subscriber_id: 'subscriber', p_manage_token: '11111111-1111-4111-8111-111111111111',
      p_topics: [], p_districts: [], p_candidates: [], p_subjects: ['2026-general'], p_receive_council_updates: false,
    })
    expect((await response.json()).preferences).toEqual({ topics: [], districts: [], candidates: [], subjects: ['2026-general'], receiveCouncilUpdates: false })
  })
  it('preserves newly added categories when an old client omits them', async () => {
    const response = await PATCH(request({ topics: [], districts: [], candidates: [] }))
    expect(response.status).toBe(200)
    expect(mocks.rpc).toHaveBeenCalledWith('replace_email_preferences_v2', expect.objectContaining({ p_subjects: null, p_receive_council_updates: null }))
    expect((await response.json()).preferences.subjects).toEqual(['2026-general'])
  })
  it.each([{ subjects: ['invented'] }, { subjects: '2026-general' }, { receiveCouncilUpdates: 'false' }])('rejects malformed choices without replacing anything: %s', async invalid => {
    expect((await PATCH(request({ topics: [], districts: [], candidates: [], ...invalid }))).status).toBe(400)
    expect(mocks.rpc).not.toHaveBeenCalled()
  })
})
