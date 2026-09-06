import type { EmailPreference, SubscriptionPreferences } from './types'
import { isSubscriptionSubject } from './subscription-subjects'

export function groupSubscriptionPreferences(rows: Pick<EmailPreference, 'preference_type' | 'preference_value'>[], receiveCouncilUpdates: boolean): SubscriptionPreferences {
  const preferences: SubscriptionPreferences = { topics: [], districts: [], candidates: [], subjects: [], receiveCouncilUpdates }
  for (const row of rows) {
    if (row.preference_type === 'topic') preferences.topics.push(row.preference_value)
    else if (row.preference_type === 'district') preferences.districts.push(row.preference_value)
    else if (row.preference_type === 'candidate') preferences.candidates.push(row.preference_value)
    else if (row.preference_type === 'subject' && isSubscriptionSubject(row.preference_value)) preferences.subjects.push(row.preference_value)
  }
  return preferences
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
