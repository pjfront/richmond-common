import type { PendingDecision } from './types'

export type ReviewAction = 'approve' | 'reject' | 'defer' | 'reopen' | 'edit_note' | 'withdraw'
export const REVIEW_ACTIONS: readonly ReviewAction[] = ['approve', 'reject', 'defer', 'reopen', 'edit_note', 'withdraw']

// API composites extend the existing generated-row-backed type. The candidate
// is an explicitly selected nested projection, not a second database schema.
export type ReviewDecision = PendingDecision & {
  review_version: number
  review_class: 'engineering' | 'editorial'
  action_kind: 'resolve_only' | 'publish_brief'
  target_brief_id: string | null
  target_content_version: number | null
  candidate: {
    id: string
    kind: 'story_update' | 'meeting_brief' | 'finance_brief'
    subject_key: string
    title: string
    body: string
    sources: unknown
    content_version: number
    status: 'draft' | 'published' | 'rejected'
    input_fingerprint: string
    published_at: string | null
  } | null
}

export interface ReviewHistoryEntry {
  id: string
  decision_id: string
  action: ReviewAction
  actor: string
  note: string | null
  expected_version: number
  created_at: string
}

export interface ReviewQueueData {
  pending: ReviewDecision[]
  deferred: ReviewDecision[]
  recently_resolved: ReviewDecision[]
  history: ReviewHistoryEntry[]
  limited: boolean
}

export function safeEvidenceLink(value: unknown): string | null {
  if (typeof value !== 'string') return null
  if (value.startsWith('/') && !value.startsWith('//') && !value.includes('\\')) return value
  try {
    const url = new URL(value)
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return null
    return url.href
  } catch { return null }
}

export function evidenceLabel(key: string): string {
  return key.replace(/[_-]+/g, ' ').replace(/\b\w/, letter => letter.toUpperCase())
}

export function availableReviewActions(decision: ReviewDecision): ReviewAction[] {
  if (decision.action_kind === 'publish_brief' && decision.candidate?.status === 'published') {
    return ['edit_note', 'withdraw']
  }
  if (decision.status === 'pending' || decision.status === 'deferred') {
    return ['approve', 'reject', ...(decision.status === 'pending' ? ['defer' as const] : []), 'edit_note']
  }
  return ['reopen', 'edit_note']
}

export function reviewErrorMessage(code: string): string {
  const messages: Record<string, string> = {
    stale_decision: 'This decision changed in another session. Refresh and review the latest version.',
    stale_content: 'The proposed text or sources changed. A refreshed decision packet is needed before approval.',
    idempotency_conflict: 'This request identifier was already used for a different action. Refresh before trying again.',
    invalid_source: 'Publication requires named, public source links from official records or independent journalism.',
    invalid_publication: 'The proposed brief needs a title, plain text, a source fingerprint, and source links.',
    withdraw_required: 'This brief is already public. Use Withdraw with an explanation to remove it.',
    withdraw_requires_published_brief_and_note: 'Withdrawing a published brief requires an explanation.',
    already_resolved: 'This decision has already been resolved. Refresh to see its current state.',
    already_open: 'This decision is already open.',
    duplicate_open_decision: 'An open decision already covers this evidence. Refresh the queue.',
    not_found: 'This decision no longer exists.',
    unsupported_action_kind: 'This proposed action is not supported by the review queue.',
  }
  return messages[code] ?? 'The action could not be saved. Your note is still here; retry or refresh.'
}
