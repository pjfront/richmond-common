import { createHash } from 'node:crypto'
import type { SupabaseClient } from '@supabase/supabase-js'
import { buildOrientationEmail, buildRecapEmail, buildWelcomeEmail, sendEmail } from './email'
import type { Provenance } from './types'

export const MAX_BROADCAST_RECIPIENTS = 500
export const MAX_DELIVERY_RETRIES_PER_REQUEST = 50
export const DELIVERY_CONCURRENCY = 10
export const MAX_DELIVERY_ATTEMPTS = 3

export type DeliveryKind = 'welcome' | 'orientation' | 'recap' | 'digest'

export interface DeliverySubscriber {
  id: string
  email: string
  unsubscribe_token: string
  name?: string | null
  status?: string
  city_fips?: string
  subscribed_at?: string
  current_activation_id?: string | null
  current_activation_at?: string | null
  last_orientation_meeting_id?: string | null
}

export interface SubscriptionLinks {
  unsubscribeUrl: string
  manageUrl: string
}

export interface EmailContent {
  subject: string
  html: string
  text?: string
}

export interface DeliveryResult {
  subscriberId: string
  status: 'sent' | 'failed' | 'already_sent' | 'in_flight' | 'backoff' | 'manual_review'
  error?: string
  retryable?: boolean
}

export interface BroadcastResult {
  sent: number
  failed: number
  already_sent: number
  deferred: number
  manual_review: number
  total_subscribers: number
  fully_delivered: boolean
}

export interface RecapBroadcastResult extends BroadcastResult {
  emailed_at: string | null
  legacy_already_sent?: boolean
}

export interface DeliveryRetryResult extends BroadcastResult {
  pending_rows: number
  stale_deliveries: number
  cancelled: number
  fully_resolved: boolean
  backlog_remaining: boolean
}

export interface RecapDeliveryMeeting {
  id: string
  meeting_date: string
  meeting_type: string
  meeting_recap: string
  minutes_url: string | null
  meeting_recap_provenance: Provenance | null
  source: 'minutes' | 'transcript'
  recap_emailed_at: string | null
  transcript_recap_emailed_at: string | null
}

interface DeliveryClaim {
  delivery_id: string
  delivery_claim_token: string | null
  delivery_attempt: number
  delivery_disposition: 'claimed' | 'already_sent' | 'in_flight' | 'backoff' | 'manual_review'
}

type EmailSender = typeof sendEmail

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://richmondcommons.org'

export function subscriptionLinks(token: string, baseUrl = SITE_URL): SubscriptionLinks {
  const encoded = encodeURIComponent(token)
  return {
    unsubscribeUrl: `${baseUrl}/api/subscribe?token=${encoded}`,
    manageUrl: `${baseUrl}/subscribe/manage?token=${encoded}`,
  }
}

/** The completed ISO week immediately before the week containing `now`. */
export function completedDigestWeek(now = new Date()): {
  start: string
  end: string
  contentKey: string
} {
  const cursor = new Date(Date.UTC(
    now.getUTCFullYear(),
    now.getUTCMonth(),
    now.getUTCDate(),
  ))
  const mondayOffset = (cursor.getUTCDay() + 6) % 7
  cursor.setUTCDate(cursor.getUTCDate() - mondayOffset - 7)
  const start = cursor.toISOString().slice(0, 10)
  cursor.setUTCDate(cursor.getUTCDate() + 6)
  const end = cursor.toISOString().slice(0, 10)
  return { start, end, contentKey: `week:${start}` }
}

export function ensureBoundedRecipients<T>(rows: T[]): T[] {
  if (rows.length > MAX_BROADCAST_RECIPIENTS) {
    throw new Error(
      `Recipient safety cap exceeded (${rows.length} > ${MAX_BROADCAST_RECIPIENTS}). ` +
      'Use a queued delivery worker before increasing this cap.',
    )
  }
  return rows
}

export function welcomeContentKey(activationId: string): string {
  return `welcome:${activationId}`
}

export async function loadActiveSubscribers(
  supabase: SupabaseClient,
  cityFips = '0660620',
): Promise<DeliverySubscriber[]> {
  const { data, error } = await supabase
    .from('email_subscribers')
    .select('id, email, name, subscribed_at, unsubscribe_token, last_orientation_meeting_id')
    .eq('status', 'active')
    .eq('city_fips', cityFips)
    .order('id', { ascending: true })
    .limit(MAX_BROADCAST_RECIPIENTS + 1)

  if (error) throw new Error(`Failed to fetch subscribers: ${error.message}`)
  return ensureBoundedRecipients((data ?? []) as DeliverySubscriber[])
}

function firstClaim(data: unknown): DeliveryClaim | null {
  const value = Array.isArray(data) ? data[0] : data
  if (!value || typeof value !== 'object') return null
  const row = value as Partial<DeliveryClaim>
  if (!row.delivery_id || !row.delivery_disposition) return null
  return row as DeliveryClaim
}

function payloadSha256(subscriber: DeliverySubscriber, content: EmailContent): string {
  return createHash('sha256')
    .update(JSON.stringify({
      to: subscriber.email,
      subject: content.subject,
      html: content.html,
      text: content.text ?? null,
    }))
    .digest('hex')
}

function scalarString(data: unknown): string | null {
  if (typeof data === 'string') return data
  if (Array.isArray(data) && typeof data[0] === 'string') return data[0]
  return null
}

export async function deliverTrackedEmail(args: {
  supabase: SupabaseClient
  subscriber: DeliverySubscriber
  kind: DeliveryKind
  contentKey: string
  build: (links: SubscriptionLinks) => EmailContent
  sender?: EmailSender
}): Promise<DeliveryResult> {
  const { supabase, subscriber, kind, contentKey, build, sender = sendEmail } = args
  const content = build(subscriptionLinks(subscriber.unsubscribe_token))
  const claimResponse = await supabase.rpc('claim_email_delivery', {
    p_subscriber_id: subscriber.id,
    p_delivery_kind: kind,
    p_content_key: contentKey,
    p_payload_sha256: payloadSha256(subscriber, content),
    p_lease_minutes: 15,
    p_max_attempts: MAX_DELIVERY_ATTEMPTS,
  })

  if (claimResponse.error) {
    return {
      subscriberId: subscriber.id,
      status: 'failed',
      error: `Delivery claim failed: ${claimResponse.error.message}`,
    }
  }

  const claim = firstClaim(claimResponse.data)
  if (!claim) {
    return {
      subscriberId: subscriber.id,
      status: 'failed',
      error: 'Delivery claim returned no disposition',
    }
  }
  if (claim.delivery_disposition !== 'claimed') {
    return { subscriberId: subscriber.id, status: claim.delivery_disposition }
  }
  if (!claim.delivery_claim_token) {
    return {
      subscriberId: subscriber.id,
      status: 'failed',
      error: 'Delivery claim did not return a lease token',
    }
  }

  const providerKey = `rc:${kind}:${claim.delivery_id}`
  const sendResult = await sender({
    to: subscriber.email,
    ...content,
    idempotencyKey: providerKey,
  })

  if (!sendResult.success) {
    const failResponse = await supabase.rpc('fail_email_delivery', {
      p_delivery_id: claim.delivery_id,
      p_claim_token: claim.delivery_claim_token,
      p_error: sendResult.error ?? 'Email provider rejected the send',
      p_is_ambiguous: sendResult.ambiguous === true,
    })
    const terminal = scalarString(failResponse.data) === 'manual_review'
    return {
      subscriberId: subscriber.id,
      status: terminal ? 'manual_review' : 'failed',
      error: sendResult.error ?? 'Email provider rejected the send',
      retryable: !terminal && !failResponse.error,
    }
  }

  const completeResponse = await supabase.rpc('complete_email_delivery', {
    p_delivery_id: claim.delivery_id,
    p_claim_token: claim.delivery_claim_token,
    p_provider_message_id: sendResult.providerId ?? null,
  })
  const completed = completeResponse.data === true
    || (Array.isArray(completeResponse.data) && completeResponse.data[0] === true)

  if (completeResponse.error || !completed) {
    await supabase.rpc('fail_email_delivery', {
      p_delivery_id: claim.delivery_id,
      p_claim_token: claim.delivery_claim_token,
      p_error: completeResponse.error?.message
        ?? 'Provider accepted email but receipt was not recorded',
      p_is_ambiguous: true,
    })
    return {
      subscriberId: subscriber.id,
      status: 'failed',
      error: completeResponse.error?.message ?? 'Provider accepted email but receipt was not recorded',
    }
  }

  return { subscriberId: subscriber.id, status: 'sent' }
}

export async function broadcastTrackedEmail(args: {
  supabase: SupabaseClient
  subscribers: DeliverySubscriber[]
  kind: DeliveryKind
  contentKey: string
  build: (subscriber: DeliverySubscriber, links: SubscriptionLinks) => EmailContent
  sender?: EmailSender
}): Promise<BroadcastResult> {
  const subscribers = ensureBoundedRecipients(args.subscribers)
  const results: DeliveryResult[] = []

  for (let offset = 0; offset < subscribers.length; offset += DELIVERY_CONCURRENCY) {
    const batch = subscribers.slice(offset, offset + DELIVERY_CONCURRENCY)
    const batchResults = await Promise.all(batch.map((subscriber) =>
      deliverTrackedEmail({
        supabase: args.supabase,
        subscriber,
        kind: args.kind,
        contentKey: args.contentKey,
        build: (links) => args.build(subscriber, links),
        sender: args.sender,
      }),
    ))
    results.push(...batchResults)
  }

  return {
    sent: results.filter((result) => result.status === 'sent').length,
    failed: results.filter((result) => result.status === 'failed').length,
    already_sent: results.filter((result) => result.status === 'already_sent').length,
    deferred: results.filter((result) =>
      result.status === 'in_flight' || result.status === 'backoff'
    ).length,
    manual_review: results.filter((result) => result.status === 'manual_review').length,
    total_subscribers: subscribers.length,
    fully_delivered: results.every((result) =>
      result.status === 'sent' || result.status === 'already_sent'
    ),
  }
}

interface RetryDeliveryRow {
  id: string
  subscriber_id: string
  delivery_kind: 'welcome' | 'orientation'
  content_key: string
}

interface OrientationRetryMeeting {
  id: string
  city_fips: string
  meeting_date: string
  orientation_preview: string | null
  orientation_preview_provenance: Provenance | null
  agenda_url: string | null
  source_cancelled_at: string | null
}

interface DeliveryRetryTask {
  deliveryId: string
  subscriber: DeliverySubscriber
  kind: 'welcome' | 'orientation'
  contentKey: string
  build: (links: SubscriptionLinks) => EmailContent
}

const ORIENTATION_CONTENT_KEY = /^meeting:([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i

function orientationMeetingId(contentKey: string): string | null {
  return ORIENTATION_CONTENT_KEY.exec(contentKey)?.[1].toLowerCase() ?? null
}

/**
 * Retry due activation welcomes and recipient-specific orientation deliveries.
 * Both kinds share one bounded query/request budget. Meeting-level legacy
 * markers intentionally do not block a retry for an already-claimed recipient
 * row; the per-recipient ledger is authoritative for that recovery.
 */
export async function retryPendingEmailDeliveries(
  supabase: SupabaseClient,
  sender: EmailSender = sendEmail,
  maxRows = MAX_DELIVERY_RETRIES_PER_REQUEST,
): Promise<DeliveryRetryResult> {
  const boundedRows = Math.max(
    0,
    Math.min(Math.trunc(maxRows), MAX_DELIVERY_RETRIES_PER_REQUEST),
  )
  if (boundedRows === 0) {
    return {
      sent: 0,
      failed: 0,
      already_sent: 0,
      deferred: 0,
      manual_review: 0,
      total_subscribers: 0,
      fully_delivered: true,
      pending_rows: 0,
      stale_deliveries: 0,
      cancelled: 0,
      fully_resolved: true,
      backlog_remaining: false,
    }
  }
  const now = new Date().toISOString()
  const { data: rows, error: deliveryError } = await supabase
    .from('email_deliveries')
    .select('id, subscriber_id, delivery_kind, content_key')
    .in('delivery_kind', ['welcome', 'orientation'])
    .or(`status.eq.pending,and(status.eq.retry_wait,next_attempt_at.lte.${now}),and(status.eq.sending,lease_expires_at.lte.${now})`)
    .order('updated_at', { ascending: true })
    .order('id', { ascending: true })
    .limit(boundedRows + 1)

  if (deliveryError) {
    throw new Error(`Failed to fetch email retries: ${deliveryError.message}`)
  }

  const pendingRows = (rows ?? []).slice(0, boundedRows) as RetryDeliveryRow[]
  if (pendingRows.length === 0) {
    return {
      sent: 0,
      failed: 0,
      already_sent: 0,
      deferred: 0,
      manual_review: 0,
      total_subscribers: 0,
      fully_delivered: true,
      pending_rows: 0,
      stale_deliveries: 0,
      cancelled: 0,
      fully_resolved: true,
      backlog_remaining: false,
    }
  }

  const subscriberIds = [...new Set(pendingRows.map((row) => row.subscriber_id))]
  const { data: subscribers, error: subscriberError } = await supabase
    .from('email_subscribers')
    .select('id, email, name, status, city_fips, subscribed_at, current_activation_id, current_activation_at, unsubscribe_token, last_orientation_meeting_id')
    .in('id', subscriberIds)

  if (subscriberError) {
    throw new Error(`Failed to fetch email retry subscribers: ${subscriberError.message}`)
  }

  const subscribersById = new Map(
    ((subscribers ?? []) as DeliverySubscriber[]).map((subscriber) => [subscriber.id, subscriber]),
  )

  const orientationMeetingIds = [...new Set(pendingRows
    .filter((row) => row.delivery_kind === 'orientation')
    .map((row) => orientationMeetingId(row.content_key))
    .filter((id): id is string => Boolean(id)))]
  let meetingRows: OrientationRetryMeeting[] = []
  if (orientationMeetingIds.length > 0) {
    const { data: meetings, error: meetingError } = await supabase
      .from('meetings')
      .select('id, city_fips, meeting_date, orientation_preview, orientation_preview_provenance, agenda_url, source_cancelled_at')
      .in('id', orientationMeetingIds)
    if (meetingError) {
      throw new Error(`Failed to fetch orientation retry meetings: ${meetingError.message}`)
    }
    meetingRows = (meetings ?? []) as OrientationRetryMeeting[]
  }
  const meetingsById = new Map(meetingRows.map((meeting) => [meeting.id.toLowerCase(), meeting]))
  const today = now.slice(0, 10)
  const staleRows: Array<{
    id: string
    failureKind: 'invalid_content_key' | 'recipient_inactive' | 'source_unavailable' | 'legacy_superseded' | 'subscription_cycle_ended'
    reason: string
    manualReview: boolean
  }> = []
  const retryRows = pendingRows.flatMap<DeliveryRetryTask>((row) => {
    const meetingId = row.delivery_kind === 'orientation'
      ? orientationMeetingId(row.content_key)
      : null
    if (row.delivery_kind === 'orientation' && !meetingId) {
      staleRows.push({
        id: row.id,
        failureKind: 'invalid_content_key',
        reason: 'Orientation content key is not meeting:<uuid>',
        manualReview: true,
      })
      return []
    }

    const subscriber = subscribersById.get(row.subscriber_id)
    if (!subscriber || subscriber.status !== 'active' || subscriber.city_fips !== '0660620') {
      staleRows.push({
        id: row.id,
        failureKind: 'recipient_inactive',
        reason: 'Subscriber is missing, inactive, or outside Richmond',
        manualReview: false,
      })
      return []
    }

    if (row.delivery_kind === 'welcome') {
      // A rollback-era app can reactivate a subscriber by changing subscribed_at
      // without writing a fresh marker. Do not mistake the older activation's
      // pending welcome for that unrecorded cycle.
      if (!subscriber.current_activation_id
        || !subscriber.current_activation_at
        || subscriber.subscribed_at !== subscriber.current_activation_at
        || row.content_key !== welcomeContentKey(subscriber.current_activation_id)) {
        staleRows.push({
          id: row.id,
          failureKind: 'subscription_cycle_ended',
          reason: 'Welcome does not match the current activation',
          manualReview: false,
        })
        return []
      }
      return [{
        deliveryId: row.id,
        subscriber,
        kind: 'welcome' as const,
        contentKey: row.content_key,
        build: ({ unsubscribeUrl, manageUrl }: SubscriptionLinks) => buildWelcomeEmail(
          subscriber.name ?? null,
          unsubscribeUrl,
          manageUrl,
        ),
      }]
    }

    const meeting = meetingId ? meetingsById.get(meetingId) : null
    const preview = meeting?.orientation_preview
    if (!meeting || meeting.city_fips !== '0660620' || meeting.source_cancelled_at
      || typeof preview !== 'string' || preview.trim() === ''
      || meeting.meeting_date < today) {
      staleRows.push({
        id: row.id,
        failureKind: 'source_unavailable',
        reason: 'Orientation source is missing, cancelled, past, or unavailable',
        manualReview: false,
      })
      return []
    }
    if (subscriber.last_orientation_meeting_id?.toLowerCase() === meetingId) {
      staleRows.push({
        id: row.id,
        failureKind: 'legacy_superseded',
        reason: 'Subscriber legacy marker already records this orientation',
        manualReview: false,
      })
      return []
    }
    return [{
      deliveryId: row.id,
      subscriber,
      kind: 'orientation' as const,
      contentKey: row.content_key,
      build: ({ unsubscribeUrl, manageUrl }: SubscriptionLinks) => buildOrientationEmail(
        {
          id: meeting.id,
          meeting_date: meeting.meeting_date,
          orientation_preview: preview,
          orientation_preview_provenance: meeting.orientation_preview_provenance,
          agenda_url: meeting.agenda_url,
        },
        unsubscribeUrl,
        manageUrl,
      ),
    }]
  })

  let cancelled = 0
  let terminalManualReview = 0
  let terminalDeferred = 0
  for (let offset = 0; offset < staleRows.length; offset += DELIVERY_CONCURRENCY) {
    const batch = staleRows.slice(offset, offset + DELIVERY_CONCURRENCY)
    const terminalizations = await Promise.all(batch.map(({ id, failureKind, reason, manualReview }) =>
      supabase.rpc('terminalize_retryable_email_delivery', {
        p_delivery_id: id,
        p_failure_kind: failureKind,
        p_reason: reason,
        p_manual_review: manualReview,
      })
    ))
    const terminalError = terminalizations.find((response) => response.error)?.error
    if (terminalError) {
      throw new Error(`Failed to close stale email retry: ${terminalError.message}`)
    }
    terminalizations.forEach((response, index) => {
      const won = response.data === true
        || (Array.isArray(response.data) && response.data[0] === true)
      if (!won) {
        terminalDeferred += 1
      } else if (batch[index].manualReview) {
        terminalManualReview += 1
      } else {
        cancelled += 1
      }
    })
  }
  const results: DeliveryResult[] = []

  for (let offset = 0; offset < retryRows.length; offset += DELIVERY_CONCURRENCY) {
    const batch = retryRows.slice(offset, offset + DELIVERY_CONCURRENCY)
    results.push(...await Promise.all(batch.map(({ subscriber, kind, contentKey, build }) =>
      deliverTrackedEmail({
        supabase,
        subscriber,
        kind,
        contentKey,
        build,
        sender,
      }),
    )))
  }

  const providerManualReview = results.filter((result) => result.status === 'manual_review').length
  const deliveryDeferred = results.filter((result) =>
    result.status === 'in_flight' || result.status === 'backoff'
  ).length
  const fullyDelivered = results.every((result) =>
    result.status === 'sent' || result.status === 'already_sent'
  )
  const backlogRemaining = (rows ?? []).length > boundedRows
  const summary = {
    sent: results.filter((result) => result.status === 'sent').length,
    failed: results.filter((result) => result.status === 'failed').length,
    already_sent: results.filter((result) => result.status === 'already_sent').length,
    deferred: deliveryDeferred + terminalDeferred,
    manual_review: providerManualReview + terminalManualReview,
    total_subscribers: retryRows.length,
    fully_delivered: fullyDelivered,
  }
  return {
    ...summary,
    pending_rows: pendingRows.length,
    stale_deliveries: staleRows.length,
    cancelled,
    fully_resolved: fullyDelivered
      && terminalDeferred === 0
      && terminalManualReview === 0
      && !backlogRemaining,
    backlog_remaining: backlogRemaining,
  }
}

/**
 * Compatibility timestamps are only safe once every current recipient has a
 * durable `sent` row. Claim dispositions distinguish already-sent deliveries
 * from live leases and backoff, but the ledger remains the compatibility
 * timestamp authority.
 */
export async function areAllDeliveriesSent(
  supabase: SupabaseClient,
  subscribers: DeliverySubscriber[],
  kind: DeliveryKind,
  contentKey: string,
): Promise<boolean> {
  if (subscribers.length === 0) return false

  const subscriberIds = subscribers.map((subscriber) => subscriber.id)
  const { data, error } = await supabase
    .from('email_deliveries')
    .select('subscriber_id, status')
    .eq('delivery_kind', kind)
    .eq('content_key', contentKey)
    .in('subscriber_id', subscriberIds)

  if (error) return false

  const sentIds = new Set(
    (data ?? [])
      .filter((row) => row.status === 'sent')
      .map((row) => row.subscriber_id as string),
  )
  return subscriberIds.every((subscriberId) => sentIds.has(subscriberId))
}

export async function sendRecapBroadcast(
  supabase: SupabaseClient,
  meeting: RecapDeliveryMeeting,
  cityFips = '0660620',
): Promise<RecapBroadcastResult> {
  const legacyEmailedAt = meeting.recap_emailed_at
    ?? meeting.transcript_recap_emailed_at
  if (legacyEmailedAt) {
    return {
      sent: 0,
      failed: 0,
      already_sent: 0,
      deferred: 0,
      manual_review: 0,
      total_subscribers: 0,
      fully_delivered: true,
      emailed_at: legacyEmailedAt,
      legacy_already_sent: true,
    }
  }

  const subscribers = await loadActiveSubscribers(supabase, cityFips)
  const contentKey = `meeting:${meeting.id}`
  const result = await broadcastTrackedEmail({
    supabase,
    subscribers,
    kind: 'recap',
    contentKey,
    build: (_subscriber, { unsubscribeUrl, manageUrl }) => buildRecapEmail(
      meeting,
      unsubscribeUrl,
      meeting.source === 'transcript' ? 'transcript' : undefined,
      manageUrl,
    ),
  })

  const fullyDelivered = subscribers.length === 0
    ? true
    : await areAllDeliveriesSent(
      supabase,
      subscribers,
      'recap',
      contentKey,
    )
  let emailedAt: string | null = null
  if (fullyDelivered && subscribers.length > 0) {
    emailedAt = new Date().toISOString()
    const markerUpdate = meeting.source === 'transcript'
      ? {
          recap_emailed_at: emailedAt,
          transcript_recap_emailed_at: emailedAt,
        }
      : { recap_emailed_at: emailedAt }
    const { error } = await supabase
      .from('meetings')
      .update(markerUpdate)
      .eq('id', meeting.id)
    if (error) emailedAt = null
  }
  return {
    ...result,
    fully_delivered: fullyDelivered,
    emailed_at: emailedAt,
  }
}

export function filterMeetingsForTopicPreferences<T extends { id: string }>(
  meetings: T[],
  topicIds: string[],
  meetingTopicLabels: Map<string, Set<string>>,
  topicLabelsById: Map<string, string>,
): T[] {
  if (topicIds.length === 0) return meetings
  const selectedLabels = new Set(
    topicIds
      .map((id) => topicLabelsById.get(id)?.toLowerCase())
      .filter((label): label is string => Boolean(label)),
  )
  if (selectedLabels.size === 0) return []
  return meetings.filter((meeting) => {
    const labels = meetingTopicLabels.get(meeting.id) ?? new Set<string>()
    return [...labels].some((label) => selectedLabels.has(label.toLowerCase()))
  })
}
