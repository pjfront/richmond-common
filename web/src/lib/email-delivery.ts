import type { SupabaseClient } from '@supabase/supabase-js'
import { buildRecapEmail, sendEmail } from './email'
import type { Provenance } from './types'

export const MAX_BROADCAST_RECIPIENTS = 500
export const DELIVERY_CONCURRENCY = 10

export type DeliveryKind = 'welcome' | 'orientation' | 'recap' | 'digest'

export interface DeliverySubscriber {
  id: string
  email: string
  unsubscribe_token: string
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
  status: 'sent' | 'failed' | 'skipped'
  error?: string
}

export interface BroadcastResult {
  sent: number
  failed: number
  skipped: number
  total_subscribers: number
}

export interface RecapBroadcastResult extends BroadcastResult {
  fully_delivered: boolean
  emailed_at: string | null
}

export interface RecapDeliveryMeeting {
  id: string
  meeting_date: string
  meeting_type: string
  meeting_recap: string
  minutes_url: string | null
  meeting_recap_provenance: Provenance | null
  source: 'minutes' | 'transcript'
}

interface DeliveryClaim {
  delivery_id: string
  delivery_claim_token: string
  delivery_attempt: number
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

export async function loadActiveSubscribers(
  supabase: SupabaseClient,
  cityFips = '0660620',
): Promise<DeliverySubscriber[]> {
  const { data, error } = await supabase
    .from('email_subscribers')
    .select('id, email, unsubscribe_token')
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
  if (!row.delivery_id || !row.delivery_claim_token) return null
  return row as DeliveryClaim
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
  const claimResponse = await supabase.rpc('claim_email_delivery', {
    p_subscriber_id: subscriber.id,
    p_delivery_kind: kind,
    p_content_key: contentKey,
    p_lease_minutes: 15,
  })

  if (claimResponse.error) {
    return {
      subscriberId: subscriber.id,
      status: 'failed',
      error: `Delivery claim failed: ${claimResponse.error.message}`,
    }
  }

  const claim = firstClaim(claimResponse.data)
  if (!claim) return { subscriberId: subscriber.id, status: 'skipped' }

  const providerKey = `rc:${kind}:${claim.delivery_id}`
  const content = build(subscriptionLinks(subscriber.unsubscribe_token))
  const sendResult = await sender({
    to: subscriber.email,
    ...content,
    idempotencyKey: providerKey,
  })

  if (!sendResult.success) {
    await supabase.rpc('fail_email_delivery', {
      p_delivery_id: claim.delivery_id,
      p_claim_token: claim.delivery_claim_token,
      p_error: sendResult.error ?? 'Email provider rejected the send',
    })
    return {
      subscriberId: subscriber.id,
      status: 'failed',
      error: sendResult.error ?? 'Email provider rejected the send',
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
    skipped: results.filter((result) => result.status === 'skipped').length,
    total_subscribers: subscribers.length,
  }
}

/**
 * Compatibility timestamps are only safe once every current recipient has a
 * durable `sent` row. A skipped claim may mean either "already sent" or
 * "another request still holds the lease", so aggregate result counts alone
 * are not authoritative.
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

  const fullyDelivered = await areAllDeliveriesSent(
    supabase,
    subscribers,
    'recap',
    contentKey,
  )
  let emailedAt: string | null = null
  if (fullyDelivered) {
    emailedAt = new Date().toISOString()
    const { error } = await supabase
      .from('meetings')
      .update({ recap_emailed_at: emailedAt })
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
