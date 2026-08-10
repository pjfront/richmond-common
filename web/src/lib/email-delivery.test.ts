import { describe, expect, it, vi } from 'vitest'
import type { SupabaseClient } from '@supabase/supabase-js'
import {
  MAX_BROADCAST_RECIPIENTS,
  areAllDeliveriesSent,
  completedDigestWeek,
  deliverTrackedEmail,
  ensureBoundedRecipients,
  filterMeetingsForTopicPreferences,
  subscriptionLinks,
} from './email-delivery'

function rpcClient(responses: Array<{ data: unknown; error: { message: string } | null }>) {
  const rpc = vi.fn().mockImplementation(async () => responses.shift() ?? { data: null, error: null })
  return { client: { rpc } as unknown as SupabaseClient, rpc }
}

const subscriber = {
  id: 'subscriber-1',
  email: 'resident@example.com',
  unsubscribe_token: 'token value',
}

describe('email delivery identities and bounds', () => {
  it('uses the immediately completed Monday-to-Sunday digest window', () => {
    expect(completedDigestWeek(new Date('2026-08-10T18:00:00Z'))).toEqual({
      start: '2026-08-03',
      end: '2026-08-09',
      contentKey: 'week:2026-08-03',
    })
  })

  it('builds encoded unsubscribe and preference links', () => {
    expect(subscriptionLinks('a token', 'https://example.test')).toEqual({
      unsubscribeUrl: 'https://example.test/api/subscribe?token=a%20token',
      manageUrl: 'https://example.test/subscribe/manage?token=a%20token',
    })
  })

  it('fails closed before sending an unbounded recipient list', () => {
    expect(() => ensureBoundedRecipients(
      Array.from({ length: MAX_BROADCAST_RECIPIENTS + 1 }, (_, index) => index),
    )).toThrow(/Recipient safety cap exceeded/)
  })

  it('requires a durable sent row for every current recipient', async () => {
    const inQuery = vi.fn().mockResolvedValue({
      data: [{ subscriber_id: 'subscriber-1', status: 'sent' }],
      error: null,
    })
    const chain = {
      select: vi.fn().mockReturnThis(),
      eq: vi.fn().mockReturnThis(),
      in: inQuery,
    }
    const client = {
      from: vi.fn().mockReturnValue(chain),
    } as unknown as SupabaseClient

    await expect(areAllDeliveriesSent(
      client,
      [subscriber, { ...subscriber, id: 'subscriber-2' }],
      'recap',
      'meeting:123',
    )).resolves.toBe(false)

    expect(inQuery).toHaveBeenCalledWith('subscriber_id', [
      'subscriber-1',
      'subscriber-2',
    ])
  })
})

describe('deliverTrackedEmail', () => {
  it('skips a delivery that is already sent or currently leased', async () => {
    const { client, rpc } = rpcClient([{ data: [], error: null }])
    const sender = vi.fn()

    const result = await deliverTrackedEmail({
      supabase: client,
      subscriber,
      kind: 'recap',
      contentKey: 'meeting:123',
      build: () => ({ subject: 'Subject', html: '<p>Body</p>' }),
      sender,
    })

    expect(result.status).toBe('skipped')
    expect(sender).not.toHaveBeenCalled()
    expect(rpc).toHaveBeenCalledOnce()
  })

  it('records a successful provider receipt with a stable idempotency key', async () => {
    const { client, rpc } = rpcClient([
      {
        data: [{
          delivery_id: 'delivery-1',
          delivery_claim_token: 'claim-1',
          delivery_attempt: 1,
        }],
        error: null,
      },
      { data: true, error: null },
    ])
    const sender = vi.fn().mockResolvedValue({ success: true, providerId: 'provider-1' })

    const result = await deliverTrackedEmail({
      supabase: client,
      subscriber,
      kind: 'digest',
      contentKey: 'week:2026-08-03',
      build: ({ manageUrl }) => ({ subject: 'Subject', html: manageUrl }),
      sender,
    })

    expect(result.status).toBe('sent')
    expect(sender).toHaveBeenCalledWith(expect.objectContaining({
      idempotencyKey: 'rc:digest:delivery-1',
      html: expect.stringContaining('/subscribe/manage?token='),
    }))
    expect(rpc).toHaveBeenLastCalledWith('complete_email_delivery', {
      p_delivery_id: 'delivery-1',
      p_claim_token: 'claim-1',
      p_provider_message_id: 'provider-1',
    })
  })

  it('marks a provider failure retryable without recording success', async () => {
    const { client, rpc } = rpcClient([
      {
        data: [{
          delivery_id: 'delivery-2',
          delivery_claim_token: 'claim-2',
          delivery_attempt: 1,
        }],
        error: null,
      },
      { data: true, error: null },
    ])
    const sender = vi.fn().mockResolvedValue({ success: false, error: 'temporary failure' })

    const result = await deliverTrackedEmail({
      supabase: client,
      subscriber,
      kind: 'orientation',
      contentKey: 'meeting:456',
      build: () => ({ subject: 'Subject', html: '<p>Body</p>' }),
      sender,
    })

    expect(result).toEqual(expect.objectContaining({ status: 'failed', error: 'temporary failure' }))
    expect(rpc).toHaveBeenLastCalledWith('fail_email_delivery', {
      p_delivery_id: 'delivery-2',
      p_claim_token: 'claim-2',
      p_error: 'temporary failure',
    })
  })
})

describe('topic-filtered digest selection', () => {
  const meetings = [{ id: 'one' }, { id: 'two' }]
  const labels = new Map([
    ['one', new Set(['Chevron & the Refinery'])],
    ['two', new Set(['Housing & Homelessness'])],
  ])
  const byId = new Map([
    ['chevron', 'Chevron & the Refinery'],
    ['housing_development', 'Housing & Homelessness'],
  ])

  it('sends the full digest when no topic preferences exist', () => {
    expect(filterMeetingsForTopicPreferences(meetings, [], labels, byId)).toEqual(meetings)
  })

  it('matches stored preference IDs to source topic labels', () => {
    expect(filterMeetingsForTopicPreferences(meetings, ['chevron'], labels, byId)).toEqual([{ id: 'one' }])
  })

  it('returns no sections rather than inventing a topic match', () => {
    expect(filterMeetingsForTopicPreferences(meetings, ['point_molate'], labels, byId)).toEqual([])
  })
})
