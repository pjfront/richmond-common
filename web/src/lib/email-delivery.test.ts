import { describe, expect, it, vi } from 'vitest'
import type { SupabaseClient } from '@supabase/supabase-js'
import {
  MAX_BROADCAST_RECIPIENTS,
  MAX_DELIVERY_RETRIES_PER_REQUEST,
  MAX_DELIVERY_ATTEMPTS,
  activationScopedContentKey,
  areAllDeliveriesSent,
  broadcastTrackedEmail,
  completedDigestWeek,
  deliverTrackedEmail,
  ensureBoundedRecipients,
  filterMeetingsForTopicPreferences,
  retryPendingEmailDeliveries,
  subscriptionLinks,
  welcomeContentKey,
} from './email-delivery'

function rpcClient(responses: Array<{ data: unknown; error: { message: string } | null }>) {
  const rpc = vi.fn().mockImplementation(async () => responses.shift() ?? { data: null, error: null })
  return { client: { rpc } as unknown as SupabaseClient, rpc }
}

const subscriber = {
  id: 'subscriber-1',
  email: 'resident@example.com',
  unsubscribe_token: 'token value',
  name: 'Resident',
  subscribed_at: '2026-08-15T20:00:00.000Z',
  current_activation_id: '11111111-1111-4111-8111-111111111111',
  current_activation_at: '2026-08-15T20:00:00.000Z',
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

  it('gives each subscription cycle a distinct welcome identity', () => {
    expect(welcomeContentKey('11111111-1111-4111-8111-111111111111'))
      .toBe('welcome:11111111-1111-4111-8111-111111111111')
  })

  it('gives non-welcome content a distinct identity in each activation', () => {
    const meetingKey = 'meeting:22222222-2222-4222-8222-222222222222'
    expect(activationScopedContentKey(
      'orientation',
      meetingKey,
      subscriber.current_activation_id,
    )).toBe(`${meetingKey}:activation:${subscriber.current_activation_id}`)
    expect(activationScopedContentKey(
      'orientation',
      meetingKey,
      '33333333-3333-4333-8333-333333333333',
    )).not.toBe(`${meetingKey}:activation:${subscriber.current_activation_id}`)
  })

  it('requires a durable sent row for every current recipient', async () => {
    const secondSubscriber = {
      ...subscriber,
      id: 'subscriber-2',
      current_activation_id: '22222222-2222-4222-8222-222222222222',
    }
    const response = {
      data: [{
        subscriber_id: 'subscriber-1',
        status: 'sent',
        content_key: `meeting:123:activation:${subscriber.current_activation_id}`,
      }],
      error: null,
    }
    const chain: Record<string, ReturnType<typeof vi.fn>> = {}
    chain.select = vi.fn(() => chain)
    chain.eq = vi.fn(() => chain)
    chain.in = vi.fn(() => chain)
    chain.then = vi.fn((onFulfilled?: (value: typeof response) => unknown) =>
      Promise.resolve(response).then(onFulfilled)
    )
    const client = {
      from: vi.fn().mockReturnValue(chain),
    } as unknown as SupabaseClient

    await expect(areAllDeliveriesSent(
      client,
      [subscriber, secondSubscriber],
      'recap',
      'meeting:123',
    )).resolves.toBe(false)

    expect(chain.in).toHaveBeenCalledWith('content_key', [
      `meeting:123:activation:${subscriber.current_activation_id}`,
      `meeting:123:activation:${secondSubscriber.current_activation_id}`,
    ])
    expect(chain.in).toHaveBeenCalledWith('subscriber_id', [
      'subscriber-1',
      'subscriber-2',
    ])
  })
})

describe('deliverTrackedEmail', () => {
  it('reports an already-sent delivery without relabeling it as skipped', async () => {
    const { client, rpc } = rpcClient([{
      data: [{
        delivery_id: 'delivery-0',
        delivery_claim_token: null,
        delivery_attempt: 1,
        delivery_disposition: 'already_sent',
      }],
      error: null,
    }])
    const sender = vi.fn()

    const result = await deliverTrackedEmail({
      supabase: client,
      subscriber,
      kind: 'recap',
      contentKey: 'meeting:123',
      build: () => ({ subject: 'Subject', html: '<p>Body</p>' }),
      sender,
    })

    expect(result.status).toBe('already_sent')
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
          delivery_disposition: 'claimed',
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
    expect(rpc).toHaveBeenNthCalledWith(1, 'claim_email_delivery', expect.objectContaining({
      p_content_key: `week:2026-08-03:activation:${subscriber.current_activation_id}`,
      p_payload_sha256: expect.stringMatching(/^[0-9a-f]{64}$/),
      p_max_attempts: MAX_DELIVERY_ATTEMPTS,
    }))
  })

  it('marks a provider failure retryable without recording success', async () => {
    const { client, rpc } = rpcClient([
      {
        data: [{
          delivery_id: 'delivery-2',
          delivery_claim_token: 'claim-2',
          delivery_attempt: 1,
          delivery_disposition: 'claimed',
        }],
        error: null,
      },
      { data: 'retry_wait', error: null },
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
      p_is_ambiguous: false,
    })
    expect(result.retryable).toBe(true)
  })

  it('records an uncertain provider response as ambiguous', async () => {
    const { client, rpc } = rpcClient([
      {
        data: [{
          delivery_id: 'delivery-3',
          delivery_claim_token: 'claim-3',
          delivery_attempt: 1,
          delivery_disposition: 'claimed',
        }],
        error: null,
      },
      { data: 'retry_wait', error: null },
    ])
    const sender = vi.fn().mockResolvedValue({
      success: false,
      error: 'provider response unknown',
      ambiguous: true,
    })

    await deliverTrackedEmail({
      supabase: client,
      subscriber,
      kind: 'welcome',
      contentKey: welcomeContentKey(subscriber.current_activation_id),
      build: () => ({ subject: 'Subject', html: '<p>Body</p>' }),
      sender,
    })

    expect(rpc).toHaveBeenLastCalledWith('fail_email_delivery', expect.objectContaining({
      p_is_ambiguous: true,
    }))
  })

  it('does not send when retry policy requires manual review', async () => {
    const { client } = rpcClient([{
      data: [{
        delivery_id: 'delivery-4',
        delivery_claim_token: null,
        delivery_attempt: MAX_DELIVERY_ATTEMPTS,
        delivery_disposition: 'manual_review',
      }],
      error: null,
    }])
    const sender = vi.fn()

    const result = await deliverTrackedEmail({
      supabase: client,
      subscriber,
      kind: 'welcome',
      contentKey: welcomeContentKey(subscriber.current_activation_id),
      build: () => ({ subject: 'Subject', html: '<p>Body</p>' }),
      sender,
    })

    expect(result.status).toBe('manual_review')
    expect(sender).not.toHaveBeenCalled()
  })
})

describe('bounded email delivery recovery', () => {
  it('shares one 50-row budget across recovery kinds and stale cleanup', async () => {
    const dueRows = Array.from(
      { length: MAX_DELIVERY_RETRIES_PER_REQUEST + 1 },
      (_, index) => {
        const activationId = `00000000-0000-4000-8000-${index.toString(16).padStart(12, '0')}`
        return {
          id: `delivery-${index}`,
          subscriber_id: `subscriber-${index}`,
          delivery_kind: index === 1 ? 'orientation' : 'welcome',
          content_key: index === 1
            ? 'meeting:malformed-shared-budget-row'
            : `welcome:${activationId}`,
          created_at: '2026-08-15T20:00:00.000Z',
        }
      },
    )
    const deliveryQuery = {
      select: vi.fn().mockReturnThis(),
      in: vi.fn().mockReturnThis(),
      or: vi.fn().mockReturnThis(),
      order: vi.fn().mockReturnThis(),
      limit: vi.fn().mockResolvedValue({ data: dueRows, error: null }),
    }
    const subscriberQuery = {
      select: vi.fn().mockReturnThis(),
      eq: vi.fn().mockReturnThis(),
      in: vi.fn().mockResolvedValue({
        data: dueRows.slice(0, MAX_DELIVERY_RETRIES_PER_REQUEST).map((_, index) => ({
          id: `subscriber-${index}`,
          email: `resident-${index}@example.test`,
          name: null,
          status: 'active',
          city_fips: '0660620',
          subscribed_at: index === 0
            ? '2026-08-15T21:00:00.000Z'
            : '2026-08-15T20:00:00.000Z',
          current_activation_id: `00000000-0000-4000-8000-${index.toString(16).padStart(12, '0')}`,
          current_activation_at: '2026-08-15T20:00:00.000Z',
          unsubscribe_token: `token-${index}`,
        })),
        error: null,
      }),
    }
    const rpc = vi.fn().mockImplementation(async (name: string) => name === 'terminalize_retryable_email_delivery'
      ? { data: true, error: null }
      : {
          data: [{
            delivery_id: 'delivery-existing',
            delivery_claim_token: null,
            delivery_attempt: 1,
            delivery_disposition: 'already_sent',
          }],
          error: null,
        })
    const client = {
      from: vi.fn()
        .mockReturnValueOnce(deliveryQuery)
        .mockReturnValueOnce(subscriberQuery),
      rpc,
    } as unknown as SupabaseClient
    const sender = vi.fn()

    const result = await retryPendingEmailDeliveries(client, sender)

    expect(deliveryQuery.limit).toHaveBeenCalledWith(MAX_DELIVERY_RETRIES_PER_REQUEST + 1)
    expect(deliveryQuery.in).toHaveBeenCalledWith(
      'delivery_kind',
      ['welcome', 'orientation', 'recap', 'digest'],
    )
    expect(deliveryQuery.or).toHaveBeenCalledWith(expect.stringContaining('status.eq.pending'))
    expect(result.pending_rows).toBe(MAX_DELIVERY_RETRIES_PER_REQUEST)
    expect(result.total_subscribers).toBe(MAX_DELIVERY_RETRIES_PER_REQUEST - 2)
    expect(result.stale_deliveries).toBe(2)
    expect(result.cancelled).toBe(1)
    expect(result.manual_review).toBe(1)
    expect(result.backlog_remaining).toBe(true)
    expect(result.fully_resolved).toBe(false)
    expect(rpc).toHaveBeenCalledWith('terminalize_retryable_email_delivery', expect.objectContaining({
      p_delivery_id: 'delivery-0',
      p_failure_kind: 'subscription_cycle_ended',
      p_manual_review: false,
    }))
    expect(rpc).toHaveBeenCalledWith('terminalize_retryable_email_delivery', expect.objectContaining({
      p_delivery_id: 'delivery-1',
      p_failure_kind: 'invalid_content_key',
      p_manual_review: true,
    }))
    expect(rpc).toHaveBeenCalledTimes(MAX_DELIVERY_RETRIES_PER_REQUEST)
    expect(sender).not.toHaveBeenCalled()
  })

  it('rebuilds and retries a recipient orientation even when the global marker is set', async () => {
    const meetingId = '22222222-2222-4222-8222-222222222222'
    const deliveryQuery = {
      select: vi.fn().mockReturnThis(),
      in: vi.fn().mockReturnThis(),
      or: vi.fn().mockReturnThis(),
      order: vi.fn().mockReturnThis(),
      limit: vi.fn().mockResolvedValue({
        data: [{
          id: 'orientation-delivery',
          subscriber_id: subscriber.id,
          delivery_kind: 'orientation',
          content_key: `meeting:${meetingId}`,
          created_at: '2026-08-15T20:00:00.000Z',
        }],
        error: null,
      }),
    }
    const subscriberQuery = {
      select: vi.fn().mockReturnThis(),
      eq: vi.fn().mockReturnThis(),
      in: vi.fn().mockResolvedValue({
        data: [{
          ...subscriber,
          status: 'active',
          city_fips: '0660620',
          last_orientation_meeting_id: null,
        }],
        error: null,
      }),
    }
    const meetingQuery = {
      select: vi.fn().mockReturnThis(),
      in: vi.fn().mockResolvedValue({
        data: [{
          id: meetingId,
          city_fips: '0660620',
          meeting_date: '2999-01-01',
          orientation_preview: '**Housing:** Council will review the proposal.',
          orientation_preview_provenance: {
            kind: 'agenda_packet',
            agenda_url: 'https://example.test/agenda.pdf',
            as_of: '2998-12-30T12:00:00Z',
          },
          agenda_url: 'https://example.test/agenda.pdf',
          source_cancelled_at: null,
          // Returned by a permissive mock to prove this compatibility marker
          // is deliberately irrelevant to recipient-ledger recovery.
          orientation_emailed_at: '2998-12-31T12:00:00Z',
        }],
        error: null,
      }),
    }
    const rpc = vi.fn().mockImplementation(async (name: string) => {
      if (name === 'claim_email_delivery') {
        return {
          data: [{
            delivery_id: 'orientation-delivery',
            delivery_claim_token: 'claim-orientation',
            delivery_attempt: 2,
            delivery_disposition: 'claimed',
          }],
          error: null,
        }
      }
      if (name === 'complete_email_delivery') return { data: true, error: null }
      return { data: null, error: null }
    })
    const client = {
      from: vi.fn()
        .mockReturnValueOnce(deliveryQuery)
        .mockReturnValueOnce(subscriberQuery)
        .mockReturnValueOnce(meetingQuery),
      rpc,
    } as unknown as SupabaseClient
    const sender = vi.fn().mockResolvedValue({ success: true, providerId: 'provider-orientation' })

    const result = await retryPendingEmailDeliveries(client, sender)

    expect(meetingQuery.in).toHaveBeenCalledWith('id', [meetingId])
    expect(rpc).toHaveBeenCalledWith('claim_email_delivery', expect.objectContaining({
      p_delivery_kind: 'orientation',
      p_content_key: `meeting:${meetingId}`,
      p_payload_sha256: expect.stringMatching(/^[0-9a-f]{64}$/),
    }))
    expect(sender).toHaveBeenCalledWith(expect.objectContaining({
      to: subscriber.email,
      subject: expect.stringContaining("What's on the agenda for"),
      html: expect.stringContaining('Council will review the proposal.'),
      text: expect.stringContaining('This preview was auto-generated from the official agenda packet.'),
    }))
    expect(result).toEqual(expect.objectContaining({
      sent: 1,
      stale_deliveries: 0,
      fully_resolved: true,
    }))
    expect(client.from).toHaveBeenCalledTimes(3)
  })

  it('never loads or sends a malformed orientation key and makes it manual', async () => {
    const deliveryQuery = {
      select: vi.fn().mockReturnThis(),
      in: vi.fn().mockReturnThis(),
      or: vi.fn().mockReturnThis(),
      order: vi.fn().mockReturnThis(),
      limit: vi.fn().mockResolvedValue({
        data: [{
          id: 'invalid-orientation',
          subscriber_id: subscriber.id,
          delivery_kind: 'orientation',
          content_key: 'meeting:not-a-uuid:extra',
          created_at: '2026-08-15T20:00:00.000Z',
        }],
        error: null,
      }),
    }
    const subscriberQuery = {
      select: vi.fn().mockReturnThis(),
      eq: vi.fn().mockReturnThis(),
      in: vi.fn().mockResolvedValue({
        data: [{ ...subscriber, status: 'active', city_fips: '0660620' }],
        error: null,
      }),
    }
    const rpc = vi.fn().mockResolvedValue({ data: true, error: null })
    const client = {
      from: vi.fn()
        .mockReturnValueOnce(deliveryQuery)
        .mockReturnValueOnce(subscriberQuery),
      rpc,
    } as unknown as SupabaseClient
    const sender = vi.fn()

    const result = await retryPendingEmailDeliveries(client, sender)

    expect(client.from).toHaveBeenCalledTimes(2)
    expect(sender).not.toHaveBeenCalled()
    expect(rpc).toHaveBeenCalledWith('terminalize_retryable_email_delivery', expect.objectContaining({
      p_failure_kind: 'invalid_content_key',
      p_manual_review: true,
    }))
    expect(result).toEqual(expect.objectContaining({
      manual_review: 1,
      fully_delivered: false,
      fully_resolved: false,
    }))
  })

  it('terminally cancels inactive, missing-source, past, cancelled, blank, and legacy-superseded rows', async () => {
    const meetingIds = Array.from(
      { length: 7 },
      (_, index) => `${index + 1}0000000-0000-4000-8000-000000000000`,
    )
    const dueRows = meetingIds.map((meetingId, index) => ({
      id: `stale-orientation-${index}`,
      subscriber_id: `stale-subscriber-${index}`,
      delivery_kind: 'orientation',
      content_key: `meeting:${meetingId}`,
      created_at: '2026-08-15T20:00:00.000Z',
    }))
    const deliveryQuery = {
      select: vi.fn().mockReturnThis(),
      in: vi.fn().mockReturnThis(),
      or: vi.fn().mockReturnThis(),
      order: vi.fn().mockReturnThis(),
      limit: vi.fn().mockResolvedValue({ data: dueRows, error: null }),
    }
    const subscriberQuery = {
      select: vi.fn().mockReturnThis(),
      eq: vi.fn().mockReturnThis(),
      in: vi.fn().mockResolvedValue({
        data: meetingIds.map((meetingId, index) => ({
          ...subscriber,
          id: `stale-subscriber-${index}`,
          status: index === 0 ? 'unsubscribed' : 'active',
          city_fips: index === 6 ? '0000000' : '0660620',
          last_orientation_meeting_id: index === 2 ? meetingId : null,
        })),
        error: null,
      }),
    }
    const meeting = (index: number, overrides: Record<string, unknown> = {}) => ({
      id: meetingIds[index],
      city_fips: '0660620',
      meeting_date: '2999-01-01',
      orientation_preview: 'A current agenda preview.',
      orientation_preview_provenance: null,
      agenda_url: null,
      source_cancelled_at: null,
      ...overrides,
    })
    const meetingQuery = {
      select: vi.fn().mockReturnThis(),
      in: vi.fn().mockResolvedValue({
        // Index 1 is intentionally absent (deleted/missing source).
        data: [
          meeting(0),
          meeting(2),
          meeting(3, { source_cancelled_at: '2026-08-15T00:00:00Z' }),
          meeting(4, { meeting_date: '2000-01-01' }),
          meeting(5, { orientation_preview: '   ' }),
          meeting(6),
        ],
        error: null,
      }),
    }
    const rpc = vi.fn().mockResolvedValue({ data: true, error: null })
    const client = {
      from: vi.fn()
        .mockReturnValueOnce(deliveryQuery)
        .mockReturnValueOnce(subscriberQuery)
        .mockReturnValueOnce(meetingQuery),
      rpc,
    } as unknown as SupabaseClient
    const sender = vi.fn()

    const result = await retryPendingEmailDeliveries(client, sender)

    expect(sender).not.toHaveBeenCalled()
    expect(result).toEqual(expect.objectContaining({
      stale_deliveries: 7,
      cancelled: 7,
      manual_review: 0,
      fully_delivered: false,
      fully_resolved: true,
    }))
    expect(rpc).toHaveBeenCalledWith('terminalize_retryable_email_delivery', expect.objectContaining({
      p_failure_kind: 'recipient_inactive',
    }))
    expect(rpc).toHaveBeenCalledWith('terminalize_retryable_email_delivery', expect.objectContaining({
      p_failure_kind: 'source_unavailable',
    }))
    expect(rpc).toHaveBeenCalledWith('terminalize_retryable_email_delivery', expect.objectContaining({
      p_failure_kind: 'legacy_superseded',
    }))
  })

  it('reports a lost terminalization race as deferred without sending', async () => {
    const deliveryQuery = {
      select: vi.fn().mockReturnThis(),
      in: vi.fn().mockReturnThis(),
      or: vi.fn().mockReturnThis(),
      order: vi.fn().mockReturnThis(),
      limit: vi.fn().mockResolvedValue({
        data: [{
          id: 'raced-invalid-orientation',
          subscriber_id: subscriber.id,
          delivery_kind: 'orientation',
          content_key: 'meeting:not-valid',
          created_at: '2026-08-15T20:00:00.000Z',
        }],
        error: null,
      }),
    }
    const subscriberQuery = {
      select: vi.fn().mockReturnThis(),
      eq: vi.fn().mockReturnThis(),
      in: vi.fn().mockResolvedValue({
        data: [{ ...subscriber, status: 'active', city_fips: '0660620' }],
        error: null,
      }),
    }
    const client = {
      from: vi.fn()
        .mockReturnValueOnce(deliveryQuery)
        .mockReturnValueOnce(subscriberQuery),
      rpc: vi.fn().mockResolvedValue({ data: false, error: null }),
    } as unknown as SupabaseClient
    const sender = vi.fn()

    const result = await retryPendingEmailDeliveries(client, sender)

    expect(sender).not.toHaveBeenCalled()
    expect(result).toEqual(expect.objectContaining({
      deferred: 1,
      manual_review: 0,
      fully_resolved: false,
    }))
  })

  it('marks a partial broadcast incomplete without a generic skipped bucket', async () => {
    const { client } = rpcClient([
      {
        data: [{
          delivery_id: 'delivery-1',
          delivery_claim_token: null,
          delivery_attempt: 1,
          delivery_disposition: 'already_sent',
        }],
        error: null,
      },
      {
        data: [{
          delivery_id: 'delivery-2',
          delivery_claim_token: null,
          delivery_attempt: 1,
          delivery_disposition: 'backoff',
        }],
        error: null,
      },
    ])

    const result = await broadcastTrackedEmail({
      supabase: client,
      subscribers: [subscriber, { ...subscriber, id: 'subscriber-2' }],
      kind: 'digest',
      contentKey: 'week:2026-08-10',
      build: () => ({ subject: 'Subject', html: '<p>Body</p>' }),
    })

    expect(result).toEqual(expect.objectContaining({
      already_sent: 1,
      deferred: 1,
      fully_delivered: false,
    }))
    expect(result).not.toHaveProperty('skipped')
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
