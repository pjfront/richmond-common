import { createHash } from 'node:crypto'
import type { SupabaseClient } from '@supabase/supabase-js'
import {
  buildDigestEmail,
  buildOrientationEmail,
  buildRecapEmail,
  buildWelcomeEmail,
  sendEmail,
} from './email'
import {
  RECAP_SOURCE_COLUMNS,
  selectPersistedRecap,
  type PersistedRecapSource,
  type SelectedPersistedRecap,
} from './email-content-source'
import { RICHMOND_LOCAL_ISSUES } from './local-issues'
import type { Provenance } from './types'

export const MAX_BROADCAST_RECIPIENTS = 500
export const MAX_DELIVERY_RETRIES_PER_REQUEST = 50
export const DELIVERY_CONCURRENCY = 10
export const MAX_DELIVERY_ATTEMPTS = 3
export const DELIVERY_STATUS_QUERY_BATCH_SIZE = 25

const UUID_VALUE = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
const UUID_VALUE_RE = new RegExp(`^${UUID_VALUE}$`, 'i')
const ACTIVATION_SUFFIX = new RegExp(`:activation:(${UUID_VALUE})$`, 'i')

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

export interface CurrentDeliveryRow {
  subscriber_id: string
  status: string
  content_key: string
}

export type RecapDeliveryMeeting = SelectedPersistedRecap

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

/**
 * Scope non-welcome idempotency to the current authorization cycle. Legacy
 * subscribers without an activation marker keep their pre-ledger identity.
 */
export function activationScopedContentKey(
  kind: DeliveryKind,
  contentKey: string,
  activationId?: string | null,
): string {
  if (kind === 'welcome' || !activationId) return contentKey
  const normalizedActivationId = activationId.toLowerCase()
  if (!UUID_VALUE_RE.test(normalizedActivationId)) {
    throw new Error('Subscriber activation id is invalid')
  }
  const existingActivationId = ACTIVATION_SUFFIX.exec(contentKey)?.[1]?.toLowerCase()
  if (existingActivationId) {
    if (existingActivationId !== normalizedActivationId) {
      throw new Error('Delivery content key belongs to another subscription cycle')
    }
    return contentKey
  }
  return `${contentKey}:activation:${normalizedActivationId}`
}

export async function loadActiveSubscribers(
  supabase: SupabaseClient,
  cityFips = '0660620',
): Promise<DeliverySubscriber[]> {
  const { data, error } = await supabase
    .from('email_subscribers')
    .select('id, email, name, subscribed_at, current_activation_id, current_activation_at, unsubscribe_token, last_orientation_meeting_id')
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
  /** Recovery only: use the exact identity of an already-persisted row. */
  contentKeyIsPersisted?: boolean
}): Promise<DeliveryResult> {
  const { supabase, subscriber, kind, build, sender = sendEmail } = args
  const contentKey = args.contentKeyIsPersisted
    ? args.contentKey
    : activationScopedContentKey(kind, args.contentKey, subscriber.current_activation_id)
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
  delivery_kind: DeliveryKind
  content_key: string
  created_at: string
}

interface RetryMeeting extends PersistedRecapSource {
  orientation_preview: string | null
  orientation_preview_provenance: Provenance | null
  agenda_url: string | null
}

interface DeliveryRetryTask {
  deliveryId: string
  subscriber: DeliverySubscriber
  kind: DeliveryKind
  contentKey: string
  build: (links: SubscriptionLinks) => EmailContent
}

interface DigestPeriod {
  start: string
  end: string
  contentKey: string
}

type ParsedRetryContent =
  | { kind: 'welcome'; activationId: string }
  | { kind: 'orientation'; meetingId: string; activationId: string | null }
  | { kind: 'recap'; meetingId: string; activationId: string | null }
  | { kind: 'digest'; period: DigestPeriod; activationId: string | null }

const RICHMOND_FIPS = '0660620'
const UUID_PART = `(${UUID_VALUE})`
const WELCOME_CONTENT_KEY = new RegExp(`^welcome:${UUID_PART}$`, 'i')
const MEETING_CONTENT_KEY = new RegExp(
  `^meeting:${UUID_PART}(?::activation:${UUID_PART})?$`,
  'i',
)
const DIGEST_CONTENT_KEY = new RegExp(
  `^week:(\\d{4}-\\d{2}-\\d{2})(?::activation:${UUID_PART})?$`,
  'i',
)
const RETRY_MEETING_COLUMNS = `${RECAP_SOURCE_COLUMNS}, orientation_preview, orientation_preview_provenance, agenda_url`
const MAX_DIGEST_SOURCE_ROWS = 250
export const MAX_DIGEST_MEETINGS_PER_WEEK = 50
export const MAX_DIGEST_PREFERENCE_ROWS = 1_000
export const MAX_DIGEST_TOPIC_ROWS = 5_000

function parseIsoDate(value: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null
  const parsed = new Date(`${value}T00:00:00.000Z`)
  if (Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== value) {
    return null
  }
  return parsed
}

function parseDigestPeriod(contentKey: string): DigestPeriod | null {
  const startValue = DIGEST_CONTENT_KEY.exec(contentKey)?.[1]
  if (!startValue) return null
  const startDate = parseIsoDate(startValue)
  if (!startDate || startDate.getUTCDay() !== 1) return null
  const endDate = new Date(startDate)
  endDate.setUTCDate(endDate.getUTCDate() + 6)
  return {
    start: startValue,
    end: endDate.toISOString().slice(0, 10),
    contentKey: `week:${startValue}`,
  }
}

function parseRetryContent(row: RetryDeliveryRow): ParsedRetryContent | null {
  if (row.delivery_kind === 'welcome') {
    const activationId = WELCOME_CONTENT_KEY.exec(row.content_key)?.[1]
    return activationId
      ? { kind: 'welcome', activationId: activationId.toLowerCase() }
      : null
  }
  if (row.delivery_kind === 'orientation' || row.delivery_kind === 'recap') {
    const match = MEETING_CONTENT_KEY.exec(row.content_key)
    const meetingId = match?.[1]
    return meetingId
      ? {
          kind: row.delivery_kind,
          meetingId: meetingId.toLowerCase(),
          activationId: match?.[2]?.toLowerCase() ?? null,
        }
      : null
  }
  const digestMatch = DIGEST_CONTENT_KEY.exec(row.content_key)
  const period = parseDigestPeriod(row.content_key)
  return period
    ? {
        kind: 'digest',
        period,
        activationId: digestMatch?.[2]?.toLowerCase() ?? null,
      }
    : null
}

/**
 * Retry all four durable delivery kinds with one 50-row budget. Content is
 * rebuilt only from bounded persisted sources. Rows from a prior subscription
 * activation, retired content, and recipients who are no longer eligible are
 * terminally cancelled; malformed identities and payload drift stop for
 * manual review rather than risking an unintended send.
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
  const emptyResult = (): DeliveryRetryResult => ({
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
  })
  if (boundedRows === 0) return emptyResult()

  const now = new Date().toISOString()
  const { data: rows, error: deliveryError } = await supabase
    .from('email_deliveries')
    .select('id, subscriber_id, delivery_kind, content_key, created_at')
    .in('delivery_kind', ['welcome', 'orientation', 'recap', 'digest'])
    .or(`status.eq.pending,and(status.eq.retry_wait,next_attempt_at.lte.${now}),and(status.eq.sending,lease_expires_at.lte.${now})`)
    .order('updated_at', { ascending: true })
    .order('id', { ascending: true })
    .limit(boundedRows + 1)

  if (deliveryError) {
    throw new Error(`Failed to fetch email retries: ${deliveryError.message}`)
  }

  const pendingRows = (rows ?? []).slice(0, boundedRows) as RetryDeliveryRow[]
  if (pendingRows.length === 0) return emptyResult()

  const subscriberIds = [...new Set(pendingRows.map((row) => row.subscriber_id))]
  const { data: subscribers, error: subscriberError } = await supabase
    .from('email_subscribers')
    .select('id, email, name, status, city_fips, subscribed_at, current_activation_id, current_activation_at, unsubscribe_token, last_orientation_meeting_id')
    .eq('status', 'active')
    .eq('city_fips', RICHMOND_FIPS)
    .in('id', subscriberIds)

  if (subscriberError) {
    throw new Error(`Failed to fetch email retry subscribers: ${subscriberError.message}`)
  }

  const subscribersById = new Map(
    ((subscribers ?? []) as DeliverySubscriber[]).map((subscriber) => [subscriber.id, subscriber]),
  )
  const staleRows: Array<{
    id: string
    failureKind: 'invalid_content_key' | 'recipient_inactive' | 'source_unavailable' | 'legacy_superseded' | 'subscription_cycle_ended'
    reason: string
    manualReview: boolean
  }> = []
  const candidates: Array<{
    row: RetryDeliveryRow
    parsed: ParsedRetryContent
    subscriber: DeliverySubscriber
  }> = []

  for (const row of pendingRows) {
    const parsed = parseRetryContent(row)
    if (!parsed) {
      staleRows.push({
        id: row.id,
        failureKind: 'invalid_content_key',
        reason: `${row.delivery_kind} content key has an invalid shape`,
        manualReview: true,
      })
      continue
    }

    const subscriber = subscribersById.get(row.subscriber_id)
    if (!subscriber || subscriber.status !== 'active'
      || subscriber.city_fips !== RICHMOND_FIPS) {
      staleRows.push({
        id: row.id,
        failureKind: 'recipient_inactive',
        reason: 'Subscriber is missing, inactive, or outside Richmond',
        manualReview: false,
      })
      continue
    }

    const createdAt = Date.parse(row.created_at)
    const activationAt = subscriber.current_activation_at
      ? Date.parse(subscriber.current_activation_at)
      : null
    if (!Number.isFinite(createdAt)
      || (activationAt !== null && !Number.isFinite(activationAt))) {
      staleRows.push({
        id: row.id,
        failureKind: 'invalid_content_key',
        reason: 'Delivery or activation timestamp is malformed',
        manualReview: true,
      })
      continue
    }
    if (activationAt !== null && createdAt < activationAt) {
      staleRows.push({
        id: row.id,
        failureKind: 'subscription_cycle_ended',
        reason: 'Delivery predates the subscriber current activation',
        manualReview: false,
      })
      continue
    }

    if (parsed.kind !== 'welcome' && parsed.activationId
      && parsed.activationId !== subscriber.current_activation_id?.toLowerCase()) {
      staleRows.push({
        id: row.id,
        failureKind: 'subscription_cycle_ended',
        reason: 'Delivery identity belongs to another subscription cycle',
        manualReview: false,
      })
      continue
    }

    if (parsed.kind === 'welcome') {
      const subscribedAt = subscriber.subscribed_at
        ? Date.parse(subscriber.subscribed_at)
        : Number.NaN
      if (!subscriber.current_activation_id
        || activationAt === null
        || !Number.isFinite(subscribedAt)
        || subscribedAt !== activationAt
        || parsed.activationId !== subscriber.current_activation_id.toLowerCase()) {
        staleRows.push({
          id: row.id,
          failureKind: 'subscription_cycle_ended',
          reason: 'Welcome does not match the current activation',
          manualReview: false,
        })
        continue
      }
    }

    if (parsed.kind === 'digest') {
      const createdWeek = completedDigestWeek(new Date(createdAt))
      if (createdWeek.contentKey !== parsed.period.contentKey) {
        staleRows.push({
          id: row.id,
          failureKind: 'invalid_content_key',
          reason: 'Digest key does not match the completed week at delivery creation',
          manualReview: true,
        })
        continue
      }
    }

    candidates.push({ row, parsed, subscriber })
  }

  const directMeetingIds = [...new Set(candidates.flatMap(({ parsed }) =>
    parsed.kind === 'orientation' || parsed.kind === 'recap'
      ? [parsed.meetingId]
      : []
  ))]
  let directMeetings: RetryMeeting[] = []
  if (directMeetingIds.length > 0) {
    const { data: meetings, error: meetingError } = await supabase
      .from('meetings')
      .select(RETRY_MEETING_COLUMNS)
      .in('id', directMeetingIds)
    if (meetingError) {
      throw new Error(`Failed to fetch meeting email retry sources: ${meetingError.message}`)
    }
    directMeetings = (meetings ?? []) as unknown as RetryMeeting[]
  }
  const directMeetingsById = new Map(
    directMeetings.map((meeting) => [meeting.id.toLowerCase(), meeting]),
  )

  const digestPeriodsByKey = new Map<string, DigestPeriod>()
  const digestSubscriberIds = new Set<string>()
  for (const candidate of candidates) {
    if (candidate.parsed.kind !== 'digest') continue
    digestPeriodsByKey.set(candidate.parsed.period.contentKey, candidate.parsed.period)
    digestSubscriberIds.add(candidate.subscriber.id)
  }

  let digestSources: PersistedRecapSource[] = []
  if (digestPeriodsByKey.size > 0) {
    const periodFilter = [...digestPeriodsByKey.values()]
      .map((period) => `and(meeting_date.gte.${period.start},meeting_date.lte.${period.end})`)
      .join(',')
    const { data: meetings, error: meetingError } = await supabase
      .from('meetings')
      .select(RECAP_SOURCE_COLUMNS)
      .eq('city_fips', RICHMOND_FIPS)
      .or(periodFilter)
      .order('meeting_date', { ascending: false })
      .order('id', { ascending: true })
      .limit(MAX_DIGEST_SOURCE_ROWS + 1)
    if (meetingError) {
      throw new Error(`Failed to fetch digest retry sources: ${meetingError.message}`)
    }
    if ((meetings ?? []).length > MAX_DIGEST_SOURCE_ROWS) {
      throw new Error(`Digest retry source cap exceeded (${MAX_DIGEST_SOURCE_ROWS})`)
    }
    digestSources = (meetings ?? []) as unknown as PersistedRecapSource[]
  }

  const preferencesBySubscriber = new Map<string, string[]>()
  if (digestSubscriberIds.size > 0) {
    const { data: preferences, error: preferenceError } = await supabase
      .from('email_preferences')
      .select('subscriber_id, preference_value')
      .eq('preference_type', 'topic')
      .in('subscriber_id', [...digestSubscriberIds])
      .limit(MAX_DIGEST_PREFERENCE_ROWS + 1)
    if (preferenceError) {
      throw new Error(`Failed to fetch digest retry preferences: ${preferenceError.message}`)
    }
    if ((preferences ?? []).length > MAX_DIGEST_PREFERENCE_ROWS) {
      throw new Error(`Digest retry preference cap exceeded (${MAX_DIGEST_PREFERENCE_ROWS})`)
    }
    for (const row of preferences ?? []) {
      const subscriberId = row.subscriber_id as string
      const values = preferencesBySubscriber.get(subscriberId) ?? []
      values.push(row.preference_value as string)
      preferencesBySubscriber.set(subscriberId, values)
    }
  }

  const digestRecapsByPeriod = new Map<string, RecapDeliveryMeeting[]>()
  for (const period of digestPeriodsByKey.values()) {
    const recaps = digestSources
      .filter((meeting) => meeting.meeting_date >= period.start && meeting.meeting_date <= period.end)
      .map(selectPersistedRecap)
      .filter((meeting): meeting is RecapDeliveryMeeting => Boolean(meeting))
      .sort((left, right) => right.meeting_date.localeCompare(left.meeting_date)
        || left.id.localeCompare(right.id))
    if (recaps.length > MAX_DIGEST_MEETINGS_PER_WEEK) {
      throw new Error(`Digest retry meeting cap exceeded for ${period.contentKey}`)
    }
    digestRecapsByPeriod.set(period.contentKey, recaps)
  }

  const digestMeetingIds = [...new Set(
    [...digestRecapsByPeriod.values()].flatMap((meetings) => meetings.map((meeting) => meeting.id)),
  )]
  const needsTopicLabels = [...preferencesBySubscriber.values()]
    .some((preferences) => preferences.length > 0)
  const meetingTopicLabels = new Map<string, Set<string>>()
  if (needsTopicLabels && digestMeetingIds.length > 0) {
    const { data: topicRows, error: topicError } = await supabase
      .from('agenda_items')
      .select('meeting_id, topic_label')
      .in('meeting_id', digestMeetingIds)
      .is('agenda_source_retired_at', null)
      .not('topic_label', 'is', null)
      .limit(MAX_DIGEST_TOPIC_ROWS + 1)
    if (topicError) {
      throw new Error(`Failed to fetch digest retry topics: ${topicError.message}`)
    }
    if ((topicRows ?? []).length > MAX_DIGEST_TOPIC_ROWS) {
      throw new Error(`Digest retry topic cap exceeded (${MAX_DIGEST_TOPIC_ROWS})`)
    }
    for (const row of topicRows ?? []) {
      const meetingId = row.meeting_id as string
      const labels = meetingTopicLabels.get(meetingId) ?? new Set<string>()
      labels.add(row.topic_label as string)
      meetingTopicLabels.set(meetingId, labels)
    }
  }

  const topicLabelsById = new Map(
    RICHMOND_LOCAL_ISSUES.map((issue) => [issue.id, issue.label]),
  )
  const today = now.slice(0, 10)
  const retryRows: DeliveryRetryTask[] = []
  for (const { row, parsed, subscriber } of candidates) {
    if (parsed.kind === 'welcome') {
      retryRows.push({
        deliveryId: row.id,
        subscriber,
        kind: 'welcome',
        contentKey: row.content_key,
        build: ({ unsubscribeUrl, manageUrl }) => buildWelcomeEmail(
          subscriber.name ?? null,
          unsubscribeUrl,
          manageUrl,
        ),
      })
      continue
    }

    if (parsed.kind === 'orientation') {
      const meeting = directMeetingsById.get(parsed.meetingId)
      const preview = meeting?.orientation_preview
      if (!meeting || meeting.city_fips !== RICHMOND_FIPS || meeting.source_cancelled_at
        || typeof preview !== 'string' || preview.trim() === ''
        || meeting.meeting_date < today) {
        staleRows.push({
          id: row.id,
          failureKind: 'source_unavailable',
          reason: 'Orientation source is missing, cancelled, past, or unavailable',
          manualReview: false,
        })
        continue
      }
      if (subscriber.last_orientation_meeting_id?.toLowerCase() === parsed.meetingId) {
        staleRows.push({
          id: row.id,
          failureKind: 'legacy_superseded',
          reason: 'Subscriber legacy marker already records this orientation',
          manualReview: false,
        })
        continue
      }
      retryRows.push({
        deliveryId: row.id,
        subscriber,
        kind: 'orientation',
        contentKey: row.content_key,
        build: ({ unsubscribeUrl, manageUrl }) => buildOrientationEmail(
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
      })
      continue
    }

    if (parsed.kind === 'recap') {
      const source = directMeetingsById.get(parsed.meetingId)
      const recap = source?.city_fips === RICHMOND_FIPS
        ? selectPersistedRecap(source)
        : null
      if (!recap || recap.meeting_date > today) {
        staleRows.push({
          id: row.id,
          failureKind: 'source_unavailable',
          reason: 'Recap source is missing, cancelled, future, or unavailable',
          manualReview: false,
        })
        continue
      }
      if (recap.recap_emailed_at || recap.transcript_recap_emailed_at) {
        staleRows.push({
          id: row.id,
          failureKind: 'legacy_superseded',
          reason: 'Meeting legacy marker already records recap delivery',
          manualReview: false,
        })
        continue
      }
      retryRows.push({
        deliveryId: row.id,
        subscriber,
        kind: 'recap',
        contentKey: row.content_key,
        build: ({ unsubscribeUrl, manageUrl }) => buildRecapEmail(
          recap,
          unsubscribeUrl,
          recap.source === 'transcript' ? 'transcript' : undefined,
          manageUrl,
        ),
      })
      continue
    }

    const recaps = digestRecapsByPeriod.get(parsed.period.contentKey) ?? []
    const selectedRecaps = filterMeetingsForTopicPreferences(
      recaps,
      preferencesBySubscriber.get(subscriber.id) ?? [],
      meetingTopicLabels,
      topicLabelsById,
    )
    if (selectedRecaps.length === 0) {
      staleRows.push({
        id: row.id,
        failureKind: 'source_unavailable',
        reason: 'Digest has no current recap matching this subscriber preferences',
        manualReview: false,
      })
      continue
    }
    retryRows.push({
      deliveryId: row.id,
      subscriber,
      kind: 'digest',
      contentKey: row.content_key,
      build: ({ unsubscribeUrl, manageUrl }) => buildDigestEmail(
        selectedRecaps,
        unsubscribeUrl,
        manageUrl,
      ),
    })
  }

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
        contentKeyIsPersisted: true,
      }),
    )))
  }

  const providerManualReview = results.filter((result) => result.status === 'manual_review').length
  const deliveryDeferred = results.filter((result) =>
    result.status === 'in_flight' || result.status === 'backoff'
  ).length
  const attemptedDeliveriesComplete = results.every((result) =>
    result.status === 'sent' || result.status === 'already_sent'
  )
  const backlogRemaining = (rows ?? []).length > boundedRows
  const fullyDelivered = attemptedDeliveriesComplete
    && staleRows.length === 0
    && !backlogRemaining
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
    fully_resolved: attemptedDeliveriesComplete
      && terminalDeferred === 0
      && terminalManualReview === 0
      && !backlogRemaining,
    backlog_remaining: backlogRemaining,
  }
}

/** Load only each subscriber's current-cycle delivery identity in bounded URLs. */
export async function loadActivationScopedDeliveryRows(
  supabase: SupabaseClient,
  subscribers: DeliverySubscriber[],
  kind: DeliveryKind,
  contentKey: string,
): Promise<CurrentDeliveryRow[]> {
  const boundedSubscribers = ensureBoundedRecipients(subscribers)
  const pairs = boundedSubscribers.map((subscriber) => ({
    subscriberId: subscriber.id,
    contentKey: activationScopedContentKey(
      kind,
      contentKey,
      subscriber.current_activation_id,
    ),
  }))
  const rows: CurrentDeliveryRow[] = []
  const windowSize = DELIVERY_STATUS_QUERY_BATCH_SIZE * DELIVERY_CONCURRENCY

  for (let windowOffset = 0; windowOffset < pairs.length; windowOffset += windowSize) {
    const window = pairs.slice(windowOffset, windowOffset + windowSize)
    const batches = Array.from(
      { length: Math.ceil(window.length / DELIVERY_STATUS_QUERY_BATCH_SIZE) },
      (_, index) => window.slice(
        index * DELIVERY_STATUS_QUERY_BATCH_SIZE,
        (index + 1) * DELIVERY_STATUS_QUERY_BATCH_SIZE,
      ),
    )
    const batchRows = await Promise.all(batches.map(async (batch) => {
      const expectedKeys = new Map(
        batch.map((pair) => [pair.subscriberId, pair.contentKey]),
      )
      const pairFilter = batch
        .map((pair) => `and(subscriber_id.eq.${pair.subscriberId},content_key.eq.${pair.contentKey})`)
        .join(',')
      const { data, error } = await supabase
        .from('email_deliveries')
        .select('subscriber_id, status, content_key')
        .eq('delivery_kind', kind)
        .limit(DELIVERY_STATUS_QUERY_BATCH_SIZE)
        .or(pairFilter)

      if (error) {
        throw new Error(`Failed to fetch current email delivery status: ${error.message}`)
      }
      return ((data ?? []) as CurrentDeliveryRow[]).filter((row) =>
        row.content_key === expectedKeys.get(row.subscriber_id)
      )
    }))
    rows.push(...batchRows.flat())
  }

  return rows
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

  let rows: CurrentDeliveryRow[]
  try {
    rows = await loadActivationScopedDeliveryRows(
      supabase,
      subscribers,
      kind,
      contentKey,
    )
  } catch {
    return false
  }

  const sentIds = new Set(
    rows
      .filter((row) => row.status === 'sent')
      .map((row) => row.subscriber_id),
  )
  return subscribers.every((subscriber) => sentIds.has(subscriber.id))
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
