/** Public, versioned subject names shared by signup, preferences and delivery. */
export const SUBSCRIPTION_SUBJECTS = [
  { id: 'chevron-settlement-and-city-budget', label: 'Chevron settlement and the city budget', href: '/stories/chevron-settlement-and-city-budget' },
  { id: 'fire-stations-and-emergency-response', label: 'Fire stations and emergency response', href: '/stories/fire-stations-and-emergency-response' },
  { id: 'flock-cameras-and-data-privacy', label: 'Flock cameras and data privacy', href: '/stories/flock-cameras-and-data-privacy' },
  { id: '2026-general', label: 'November 2026 election and campaign money', href: '/elections/2026-general' },
] as const
export type SubscriptionSubject = typeof SUBSCRIPTION_SUBJECTS[number]['id']
export function isSubscriptionSubject(value: unknown): value is SubscriptionSubject {
  return typeof value === 'string' && SUBSCRIPTION_SUBJECTS.some(subject => subject.id === value)
}
export const SUBJECT_FOLLOW_ROLLOUT = 'Weekly story and election emails are scheduled for Mondays at 9:30 a.m. PDT / 8:30 a.m. PST, only when a story or election you follow has a newly published update.'
