import type { AgendaItemWithMotions } from './types'

export interface StageVoteSourceReview {
  reason: string
  sourceUrl: string
  checkedAt: string
}

/** One primary-document QA case; this is a display hold, never a database repair. */
export const POINT_MOLATE_VOTE_REVIEW = {
  itemId: '9cf375c8-edc1-413c-8ee0-6485348fbc6f',
  meetingId: '5f560013-daea-499a-8ecd-ca1a089c8a0c',
  itemNumber: 'j-2',
  reason: 'The indexed motions and vote choices conflict with the original minutes. Motion records and their generated summaries are held for source review.',
  sourceUrl: 'https://www.ci.richmond.ca.us/ArchiveCenter/ViewFile/Item/2809',
  checkedAt: '2026-10-03',
} as const

export function stageVoteSourceReviewForItem(item: {
  id: string; meeting_id: string; item_number: string
}): StageVoteSourceReview | null {
  // A known source conflict follows the record in every tier, including local.
  if (item.id !== POINT_MOLATE_VOTE_REVIEW.itemId
    || item.meeting_id !== POINT_MOLATE_VOTE_REVIEW.meetingId
    || item.item_number.toLowerCase() !== POINT_MOLATE_VOTE_REVIEW.itemNumber) return null
  return { reason: POINT_MOLATE_VOTE_REVIEW.reason, sourceUrl: POINT_MOLATE_VOTE_REVIEW.sourceUrl, checkedAt: POINT_MOLATE_VOTE_REVIEW.checkedAt }
}

/** Strip disputed records before serializing page props; preserve the source item. */
export function holdStageVoteSourceRecords<T extends AgendaItemWithMotions>(item: T): T {
  const review = stageVoteSourceReviewForItem(item)
  return review ? { ...item, motions: [], summary_headline: null, plain_language_summary: null,
    plain_language_summary_provenance: null, voteSourceReview: review } : item
}
