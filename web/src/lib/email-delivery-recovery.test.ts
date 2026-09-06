import { describe, expect, it, vi } from 'vitest'
import type { SupabaseClient } from '@supabase/supabase-js'
import {
  MAX_DELIVERY_RETRIES_PER_REQUEST,
  retryPendingEmailDeliveries,
  type DeliveryKind,
} from './email-delivery'

interface QueryResponse {
  data: unknown[] | null
  error: { message: string } | null
}

type QueryMock = Record<string, ReturnType<typeof vi.fn>>

function fluentQuery(response: QueryResponse): QueryMock {
  const query: QueryMock = {}
  const returnQuery = () => query
  for (const method of [
    'select', 'in', 'eq', 'or', 'order', 'limit', 'is', 'not', 'gte', 'lte',
  ]) {
    query[method] = vi.fn(returnQuery)
  }
  query.then = vi.fn((
    onFulfilled?: (value: QueryResponse) => unknown,
    onRejected?: (reason: unknown) => unknown,
  ) => Promise.resolve(response).then(onFulfilled, onRejected))
  return query
}

function recoveryClient(
  tableResponses: Record<string, QueryResponse[]>,
  rpcImplementation: (name: string, args: unknown) => Promise<QueryResponse>,
) {
  const queries = new Map<string, QueryMock[]>()
  const from = vi.fn((table: string) => {
    const response = tableResponses[table]?.shift() ?? (table === 'civic_brief_candidates' ? { data: [], error: null } : undefined)
    if (!response) throw new Error(`Unexpected query for ${table}`)
    const query = fluentQuery(response)
    const tableQueries = queries.get(table) ?? []
    tableQueries.push(query)
    queries.set(table, tableQueries)
    return query
  })
  const rpc = vi.fn(rpcImplementation)
  return {
    client: { from, rpc } as unknown as SupabaseClient,
    from,
    queries,
    rpc,
  }
}

const activationAt = '2026-08-01T12:00:00.000Z'

function activeSubscriber(id = 'subscriber-1', overrides: Record<string, unknown> = {}) {
  return {
    id,
    email: `${id}@example.test`,
    name: 'Richmond Resident',
    status: 'active',
    city_fips: '0660620',
    subscribed_at: activationAt,
    current_activation_id: '11111111-1111-4111-8111-111111111111',
    current_activation_at: activationAt,
    unsubscribe_token: `token-${id}`,
    last_orientation_meeting_id: null,
    ...overrides,
  }
}

function dueDelivery(
  kind: DeliveryKind,
  contentKey: string,
  overrides: Record<string, unknown> = {},
) {
  return {
    id: `delivery-${kind}`,
    subscriber_id: 'subscriber-1',
    delivery_kind: kind,
    content_key: contentKey,
    created_at: '2026-08-15T12:00:00.000Z',
    ...overrides,
  }
}

function recapMeeting(id: string, overrides: Record<string, unknown> = {}) {
  return {
    id,
    city_fips: '0660620',
    meeting_date: '2026-08-05',
    meeting_type: 'regular',
    meeting_recap: '**Official recap:** Minutes-confirmed result.',
    meeting_recap_provenance: {
      kind: 'official_minutes',
      minutes_url: 'https://example.test/minutes.pdf',
      as_of: '2026-08-06T00:00:00Z',
    },
    transcript_recap: '**Transcript recap:** Recording result.',
    transcript_recap_provenance: {
      kind: 'meeting_recording',
      channel: 'kcrt',
      as_of: '2026-08-05T23:00:00Z',
    },
    minutes_url: 'https://example.test/minutes.pdf',
    recap_emailed_at: null,
    transcript_recap_emailed_at: null,
    source_cancelled_at: null,
    orientation_preview: null,
    orientation_preview_provenance: null,
    agenda_url: null,
    ...overrides,
  }
}

async function successfulRpc(name: string): Promise<QueryResponse> {
  if (name === 'claim_consented_email_delivery') {
    return {
      data: [{
        delivery_id: 'claimed-delivery',
        delivery_claim_token: 'claim-token',
        delivery_attempt: 2,
        delivery_disposition: 'claimed',
      }],
      error: null,
    }
  }
  if (name === 'complete_email_delivery') return { data: [true], error: null }
  if (name === 'terminalize_retryable_email_delivery') return { data: [true], error: null }
  return { data: null, error: null }
}

describe('recap and digest delivery recovery', () => {
  it('recovers subject-only updates without adding meeting recaps and pins the approved source version', async () => {
    const brief = { id: '99999999-9999-4999-8999-999999999999', subject_key: '2026-general', title: 'Reviewed November update', body: 'A sourced proposal, not an adopted outcome.', sources: [{ title: 'Official resolution', url: 'https://www.richmondca.gov/Archive.aspx?ADID=17785', source_tier: 1, source_date: null }], content_version: 2, published_at: '2026-08-05T12:00:00Z' }
    const { client, rpc } = recoveryClient({
      email_deliveries: [{ data: [dueDelivery('digest', 'week:2026-08-03', { created_at: '2026-08-10T18:00:00Z' })], error: null }],
      email_subscribers: [{ data: [activeSubscriber('subscriber-1', { receive_council_updates: false })], error: null }],
      meetings: [{ data: [recapMeeting('11111111-2222-4333-8444-555555555555')], error: null }],
      email_preferences: [{ data: [{ subscriber_id: 'subscriber-1', preference_type: 'subject', preference_value: '2026-general' }], error: null }],
      civic_brief_candidates: [{ data: [brief], error: null }],
    }, successfulRpc)
    const sender = vi.fn().mockResolvedValue({ success: true, providerId: 'provider-subject' })
    expect((await retryPendingEmailDeliveries(client, sender)).sent).toBe(1)
    expect(sender.mock.calls[0][0].text).toContain('Reviewed November update')
    expect(sender.mock.calls[0][0].text).not.toContain('Minutes-confirmed result')
    expect(rpc).toHaveBeenCalledWith('claim_consented_email_delivery', expect.objectContaining({ p_brief_versions: [{ id: brief.id, content_version: 2, published_at: brief.published_at }] }))
  })

  it('cancels pending council mail after council consent is turned off', async () => {
    const { client, from } = recoveryClient({
      email_deliveries: [{ data: [dueDelivery('orientation', 'meeting:22222222-2222-4222-8222-222222222222'), dueDelivery('recap', 'meeting:33333333-3333-4333-8333-333333333333')], error: null }],
      email_subscribers: [{ data: [activeSubscriber('subscriber-1', { receive_council_updates: false })], error: null }],
    }, successfulRpc)
    const sender = vi.fn()
    expect((await retryPendingEmailDeliveries(client, sender)).cancelled).toBe(2)
    expect(sender).not.toHaveBeenCalled()
    expect(from).toHaveBeenCalledTimes(2)
  })

  it('cancels a subject-only digest after its published content is withdrawn', async () => {
    const { client } = recoveryClient({
      email_deliveries: [{ data: [dueDelivery('digest', 'week:2026-08-03', { created_at: '2026-08-10T18:00:00Z' })], error: null }],
      email_subscribers: [{ data: [activeSubscriber('subscriber-1', { receive_council_updates: false })], error: null }],
      meetings: [{ data: [recapMeeting('11111111-2222-4333-8444-555555555555')], error: null }],
      email_preferences: [{ data: [{ subscriber_id: 'subscriber-1', preference_type: 'subject', preference_value: '2026-general' }], error: null }],
      civic_brief_candidates: [{ data: [], error: null }],
    }, successfulRpc)
    const sender = vi.fn()
    expect((await retryPendingEmailDeliveries(client, sender)).cancelled).toBe(1)
    expect(sender).not.toHaveBeenCalled()
  })

  it('rebuilds a recap from the official-minutes artifact and matching provenance', async () => {
    const meetingId = '22222222-2222-4222-8222-222222222222'
    const { client, rpc } = recoveryClient({
      email_deliveries: [{
        data: [dueDelivery('recap', `meeting:${meetingId}`)],
        error: null,
      }],
      email_subscribers: [{ data: [activeSubscriber()], error: null }],
      meetings: [{ data: [recapMeeting(meetingId)], error: null }],
    }, successfulRpc)
    const sender = vi.fn().mockResolvedValue({ success: true, providerId: 'provider-recap' })

    const result = await retryPendingEmailDeliveries(client, sender)

    expect(result).toEqual(expect.objectContaining({ sent: 1, fully_resolved: true }))
    expect(sender).toHaveBeenCalledWith(expect.objectContaining({
      html: expect.stringContaining('Minutes-confirmed result.'),
      text: expect.stringContaining('official minutes and vote records'),
    }))
    expect(sender.mock.calls[0][0].html).not.toContain('Recording result.')
    expect(rpc).toHaveBeenCalledWith('claim_consented_email_delivery', expect.objectContaining({
      p_delivery_kind: 'recap',
      p_content_key: `meeting:${meetingId}`,
    }))
  })

  it('falls back to the transcript recap with transcript provenance', async () => {
    const meetingId = '33333333-3333-4333-8333-333333333333'
    const { client } = recoveryClient({
      email_deliveries: [{
        data: [dueDelivery('recap', `meeting:${meetingId}`)],
        error: null,
      }],
      email_subscribers: [{ data: [activeSubscriber()], error: null }],
      meetings: [{
        data: [recapMeeting(meetingId, {
          meeting_recap: null,
          meeting_recap_provenance: {
            kind: 'official_minutes',
            minutes_url: 'https://wrong.example/minutes.pdf',
            as_of: '2026-08-06T00:00:00Z',
          },
        })],
        error: null,
      }],
    }, successfulRpc)
    const sender = vi.fn().mockResolvedValue({ success: true, providerId: 'provider-transcript' })

    const result = await retryPendingEmailDeliveries(client, sender)

    expect(result.sent).toBe(1)
    expect(sender).toHaveBeenCalledWith(expect.objectContaining({
      html: expect.stringContaining('Recording result.'),
      text: expect.stringContaining('KCRT meeting recording'),
    }))
    expect(sender.mock.calls[0][0].text).not.toContain('official minutes and vote records')
  })

  it('reconstructs one digest with grouped preferences/topics and filters its sections', async () => {
    const housingId = '44444444-4444-4444-8444-444444444444'
    const refineryId = '55555555-5555-4555-8555-555555555555'
    const digest = dueDelivery('digest', 'week:2026-08-03', {
      created_at: '2026-08-10T18:00:00.000Z',
    })
    const { client, from, queries } = recoveryClient({
      email_deliveries: [{ data: [digest], error: null }],
      email_subscribers: [{ data: [activeSubscriber()], error: null }],
      meetings: [{
        data: [
          recapMeeting(housingId, {
            meeting_recap: '**Housing:** Affordable housing decision.',
          }),
          recapMeeting(refineryId, {
            meeting_date: '2026-08-04',
            meeting_recap: '**Refinery:** Air monitoring decision.',
          }),
        ],
        error: null,
      }],
      email_preferences: [{
        data: [{ subscriber_id: 'subscriber-1', preference_type: 'topic', preference_value: 'housing_development' }],
        error: null,
      }],
      agenda_items: [{
        data: [
          { meeting_id: housingId, topic_label: 'Housing & Homelessness' },
          { meeting_id: refineryId, topic_label: 'Chevron & the Refinery' },
        ],
        error: null,
      }],
    }, successfulRpc)
    const sender = vi.fn().mockResolvedValue({ success: true, providerId: 'provider-digest' })

    const result = await retryPendingEmailDeliveries(client, sender)

    expect(result.sent).toBe(1)
    expect(sender).toHaveBeenCalledWith(expect.objectContaining({
      html: expect.stringContaining('Affordable housing decision.'),
    }))
    expect(sender.mock.calls[0][0].html).not.toContain('Air monitoring decision.')
    expect(from.mock.calls.filter(([table]) => table === 'meetings')).toHaveLength(1)
    expect(from.mock.calls.filter(([table]) => table === 'email_preferences')).toHaveLength(1)
    expect(from.mock.calls.filter(([table]) => table === 'agenda_items')).toHaveLength(1)
    expect(queries.get('meetings')?.[0].or).toHaveBeenCalledOnce()
  })

  it('cancels a delivery created before the subscriber current activation', async () => {
    const meetingId = '66666666-6666-4666-8666-666666666666'
    const { client, from, rpc } = recoveryClient({
      email_deliveries: [{
        data: [dueDelivery('recap', `meeting:${meetingId}`, {
          created_at: '2026-07-31T23:59:59.000Z',
        })],
        error: null,
      }],
      email_subscribers: [{ data: [activeSubscriber()], error: null }],
    }, successfulRpc)
    const sender = vi.fn()

    const result = await retryPendingEmailDeliveries(client, sender)

    expect(result).toEqual(expect.objectContaining({ cancelled: 1, stale_deliveries: 1 }))
    expect(sender).not.toHaveBeenCalled()
    expect(from).toHaveBeenCalledTimes(2)
    expect(rpc).toHaveBeenCalledWith('terminalize_retryable_email_delivery', expect.objectContaining({
      p_failure_kind: 'subscription_cycle_ended',
      p_manual_review: false,
    }))
  })

  it('cancels a delivery scoped to a previous activation even when its timestamp is current', async () => {
    const meetingId = '67676767-6767-4767-8767-676767676767'
    const previousActivationId = '22222222-2222-4222-8222-222222222222'
    const { client, from, rpc } = recoveryClient({
      email_deliveries: [{
        data: [dueDelivery(
          'recap',
          `meeting:${meetingId}:activation:${previousActivationId}`,
        )],
        error: null,
      }],
      email_subscribers: [{ data: [activeSubscriber()], error: null }],
    }, successfulRpc)
    const sender = vi.fn()

    const result = await retryPendingEmailDeliveries(client, sender)

    expect(result).toEqual(expect.objectContaining({
      cancelled: 1,
      stale_deliveries: 1,
      fully_delivered: false,
      fully_resolved: true,
    }))
    expect(sender).not.toHaveBeenCalled()
    expect(from).toHaveBeenCalledTimes(2)
    expect(rpc).toHaveBeenCalledWith('terminalize_retryable_email_delivery', expect.objectContaining({
      p_failure_kind: 'subscription_cycle_ended',
      p_manual_review: false,
    }))
  })

  it('cancels recap retries whose source is cancelled or missing', async () => {
    const cancelledId = '77777777-7777-4777-8777-777777777777'
    const missingId = '88888888-8888-4888-8888-888888888888'
    const { client, rpc } = recoveryClient({
      email_deliveries: [{
        data: [
          dueDelivery('recap', `meeting:${cancelledId}`),
          dueDelivery('recap', `meeting:${missingId}`, {
            id: 'delivery-missing',
            subscriber_id: 'subscriber-2',
          }),
        ],
        error: null,
      }],
      email_subscribers: [{
        data: [activeSubscriber(), activeSubscriber('subscriber-2')],
        error: null,
      }],
      meetings: [{
        data: [recapMeeting(cancelledId, {
          source_cancelled_at: '2026-08-06T00:00:00.000Z',
        })],
        error: null,
      }],
    }, successfulRpc)
    const sender = vi.fn()

    const result = await retryPendingEmailDeliveries(client, sender)

    expect(result).toEqual(expect.objectContaining({ cancelled: 2, stale_deliveries: 2 }))
    expect(sender).not.toHaveBeenCalled()
    expect(rpc.mock.calls.filter(([name]) => name === 'terminalize_retryable_email_delivery'))
      .toHaveLength(2)
  })

  it('cancels a recap already covered by a pre-ledger legacy marker', async () => {
    const meetingId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
    const { client, rpc } = recoveryClient({
      email_deliveries: [{
        data: [dueDelivery('recap', `meeting:${meetingId}`)],
        error: null,
      }],
      email_subscribers: [{ data: [activeSubscriber()], error: null }],
      meetings: [{
        data: [recapMeeting(meetingId, {
          transcript_recap_emailed_at: '2026-08-06T12:00:00.000Z',
        })],
        error: null,
      }],
    }, successfulRpc)

    const result = await retryPendingEmailDeliveries(client, vi.fn())

    expect(result.cancelled).toBe(1)
    expect(rpc).toHaveBeenCalledWith('terminalize_retryable_email_delivery', expect.objectContaining({
      p_failure_kind: 'legacy_superseded',
    }))
  })

  it('cancels a digest that no longer has an eligible persisted recap', async () => {
    const { client, rpc } = recoveryClient({
      email_deliveries: [{
        data: [dueDelivery('digest', 'week:2026-08-03', {
          created_at: '2026-08-10T18:00:00.000Z',
        })],
        error: null,
      }],
      email_subscribers: [{ data: [activeSubscriber()], error: null }],
      meetings: [{ data: [], error: null }],
      email_preferences: [{ data: [], error: null }],
    }, successfulRpc)

    const result = await retryPendingEmailDeliveries(client, vi.fn())

    expect(result).toEqual(expect.objectContaining({ cancelled: 1, stale_deliveries: 1 }))
    expect(rpc).toHaveBeenCalledWith('terminalize_retryable_email_delivery', expect.objectContaining({
      p_failure_kind: 'source_unavailable',
    }))
  })

  it('terminates malformed recap and digest keys without loading sources', async () => {
    const { client, from, rpc } = recoveryClient({
      email_deliveries: [{
        data: [
          dueDelivery('recap', 'meeting:not-a-uuid'),
          dueDelivery('digest', 'week:2026-08-04', {
            id: 'delivery-bad-digest',
            subscriber_id: 'subscriber-2',
          }),
        ],
        error: null,
      }],
      email_subscribers: [{
        data: [activeSubscriber(), activeSubscriber('subscriber-2')],
        error: null,
      }],
    }, successfulRpc)
    const sender = vi.fn()

    const result = await retryPendingEmailDeliveries(client, sender)

    expect(result).toEqual(expect.objectContaining({
      manual_review: 2,
      fully_delivered: false,
      fully_resolved: false,
    }))
    expect(sender).not.toHaveBeenCalled()
    expect(from).toHaveBeenCalledTimes(2)
    expect(rpc.mock.calls.filter(([, args]) =>
      (args as { p_failure_kind?: string }).p_failure_kind === 'invalid_content_key'
    )).toHaveLength(2)
  })

  it('preserves payload-hash safety by stopping reconstructed drift for manual review', async () => {
    const meetingId = '99999999-9999-4999-8999-999999999999'
    const manualReviewRpc = async (name: string): Promise<QueryResponse> => {
      if (name === 'claim_consented_email_delivery') {
        return {
          data: [{
            delivery_id: 'drifted-delivery',
            delivery_claim_token: null,
            delivery_attempt: 1,
            delivery_disposition: 'manual_review',
          }],
          error: null,
        }
      }
      return { data: null, error: null }
    }
    const { client, rpc } = recoveryClient({
      email_deliveries: [{
        data: [dueDelivery('recap', `meeting:${meetingId}`)],
        error: null,
      }],
      email_subscribers: [{ data: [activeSubscriber()], error: null }],
      meetings: [{ data: [recapMeeting(meetingId)], error: null }],
    }, manualReviewRpc)
    const sender = vi.fn()

    const result = await retryPendingEmailDeliveries(client, sender)

    expect(result).toEqual(expect.objectContaining({ manual_review: 1, fully_resolved: false }))
    expect(sender).not.toHaveBeenCalled()
    expect(rpc).toHaveBeenCalledWith('claim_consented_email_delivery', expect.objectContaining({
      p_payload_sha256: expect.stringMatching(/^[0-9a-f]{64}$/),
    }))
  })

  it('keeps one shared 50-row budget even with recap and digest backlog', async () => {
    const rows = Array.from(
      { length: MAX_DELIVERY_RETRIES_PER_REQUEST + 1 },
      (_, index) => dueDelivery(
        index % 2 === 0 ? 'recap' : 'digest',
        index % 2 === 0
          ? 'meeting:not-valid'
          : 'week:not-valid',
        {
          id: `delivery-${index}`,
          subscriber_id: `subscriber-${index}`,
        },
      ),
    )
    const subscribers = rows.slice(0, MAX_DELIVERY_RETRIES_PER_REQUEST)
      .map((_, index) => activeSubscriber(`subscriber-${index}`))
    const { client, queries } = recoveryClient({
      email_deliveries: [{ data: rows, error: null }],
      email_subscribers: [{ data: subscribers, error: null }],
    }, successfulRpc)

    const result = await retryPendingEmailDeliveries(client, vi.fn())

    expect(result).toEqual(expect.objectContaining({
      pending_rows: MAX_DELIVERY_RETRIES_PER_REQUEST,
      backlog_remaining: true,
      manual_review: MAX_DELIVERY_RETRIES_PER_REQUEST,
      fully_delivered: false,
      fully_resolved: false,
    }))
    expect(queries.get('email_deliveries')?.[0].limit)
      .toHaveBeenCalledWith(MAX_DELIVERY_RETRIES_PER_REQUEST + 1)
    expect(queries.get('email_deliveries')?.[0].select)
      .toHaveBeenCalledWith(expect.stringContaining('created_at'))
  })
})
