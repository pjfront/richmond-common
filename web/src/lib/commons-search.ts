import type { FinanceCoverage, FinanceEvent } from './queries/finance-public'
import type { RecordedChoice } from './vote-records'

export const COMMONS_PAGE_SIZE = 20
export const COMMONS_RANKED_LIMIT = 100
export type CommonsMode = 'agenda' | 'votes' | 'money'

export interface CommonsSearchFilters {
  q: string
  mode: CommonsMode
  topic: string
  from: string
  to: string
  page: number
}

export interface CommonsSearchPlan extends CommonsSearchFilters {
  keywords: string
  moneyRole: 'source' | 'recipient' | ''
  contributionsOnly: boolean
  interpretation: string[]
}

export interface CommonsMotion {
  id: string
  text: string | null
  result: string | null
  source: string | null
  indexedAt: string
  votes: Array<{ id: string; name: string | null; choice: RecordedChoice; source: string | null }>
}

export interface CommonsAgendaRecord {
  kind: 'agenda' | 'votes'
  id: string
  title: string
  itemNumber: string
  meetingDate: string
  topic: string | null
  category: string | null
  url: string
  sourceUrl: string
  minutesUrl: string | null
  recordingUrl: string | null
  indexedAt: string
  motions: CommonsMotion[]
}

export interface CommonsMoneyRecord {
  kind: 'money'
  id: string
  event: FinanceEvent
}

export interface CommonsSearchResponse {
  filters: CommonsSearchFilters
  interpretation: string[]
  records: Array<CommonsAgendaRecord | CommonsMoneyRecord>
  topics: string[]
  hasMore: boolean
  total: number | null
  limited: boolean
  limitations: string[]
  coverage: FinanceCoverage[]
}

export class CommonsSearchInputError extends Error {}

export function isCalendarDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const date = new Date(`${value}T00:00:00Z`)
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value
}

/** A small, disclosed grammar. Unrecognized questions remain keyword searches. */
export function planCommonsSearch(params: URLSearchParams): CommonsSearchPlan {
  const q = (params.get('q') ?? '').normalize('NFKC').trim()
  if (q.length > 200) throw new CommonsSearchInputError('Use a search of 200 characters or fewer.')
  const rawMode = params.get('mode') ?? params.get('type')
  if (rawMode && !['agenda', 'votes', 'money'].includes(rawMode)) {
    throw new CommonsSearchInputError('Choose agenda items, votes, or money.')
  }
  const mode: CommonsMode = rawMode as CommonsMode | null
    ?? (/^donations?\b|^contributions?\b/i.test(q) ? 'money' : /^who voted on\b/i.test(q) ? 'votes' : 'agenda')
  const topic = (params.get('topic') ?? '').trim()
  if (topic.length > 100) throw new CommonsSearchInputError('Use a tag of 100 characters or fewer.')
  if (mode === 'money' && topic) throw new CommonsSearchInputError('Agenda tags do not apply to money records.')
  let from = params.get('from') ?? ''
  let to = params.get('to') ?? ''
  for (const date of [from, to]) {
    if (date && !isCalendarDate(date)) throw new CommonsSearchInputError('Use valid dates in YYYY-MM-DD format.')
  }
  if (from && to && from > to) throw new CommonsSearchInputError('The start date must come before the end date.')
  const rawPage = params.get('page') ?? '1'
  if (!/^\d{1,3}$/.test(rawPage) || Number(rawPage) < 1 || Number(rawPage) > 100) {
    throw new CommonsSearchInputError('Choose a result page between 1 and 100.')
  }
  let keywords = q.replace(/[?]+$/, '').replace(/^(?:show(?: me)?|find|list)\s+/i, '')
  const year = keywords.match(/\s+(?:in|during)\s+(20\d{2})$/i)
  if (year) {
    keywords = keywords.slice(0, year.index).trim()
    if (!from) from = `${year[1]}-01-01`
    if (!to) to = `${year[1]}-12-31`
  }
  let moneyRole: CommonsSearchPlan['moneyRole'] = ''
  let contributionsOnly = false
  if (mode === 'money') {
    const money = keywords.match(/^(?:donations?|contributions?)\s+(to|from)\s+(.+)$/i)
    if (money) {
      moneyRole = money[1].toLowerCase() === 'to' ? 'recipient' : 'source'
      contributionsOnly = true
      keywords = money[2].trim()
    }
  } else {
    keywords = keywords.replace(/^who voted on\s+/i, '').replace(/\s+(?:agenda items?|decisions?)$/i, '').trim()
  }
  if (from && to && from > to) throw new CommonsSearchInputError('The start date must come before the end date.')
  const interpretation = [keywords ? `Keywords: ${keywords}` : 'Browse indexed records']
  if (moneyRole) interpretation.push(`${moneyRole === 'recipient' ? 'Recipient' : 'Contributor'} name contains: ${keywords}`)
  if (contributionsOnly) interpretation.push('Cash contribution records')
  if (topic) interpretation.push(`Tag: ${topic}`)
  if (from || to) interpretation.push(`${mode === 'money' ? 'Activity' : 'Meeting'} dates: ${from || 'any start'} to ${to || 'any end'}`)
  return { q, mode, topic, from, to, page: Number(rawPage), keywords, moneyRole, contributionsOnly, interpretation }
}

export function commonsSearchParams(filters: CommonsSearchFilters): URLSearchParams {
  const { q, mode, topic, from, to, page } = filters
  return new URLSearchParams(Object.entries({ q, mode, topic, from, to, page }).filter(([key, value]) => value !== '' && !(key === 'page' && value === 1))
    .map(([key, value]) => [key, String(value)]))
}

export function matchesCommonsScope(row: Pick<CommonsAgendaRecord, 'topic' | 'meetingDate'>, plan: CommonsSearchPlan): boolean {
  return (!plan.topic || row.topic === plan.topic) && (!plan.from || row.meetingDate >= plan.from) && (!plan.to || row.meetingDate <= plan.to)
}

export function publicSourceUrl(value: string | null): string | null {
  if (!value) return null
  try {
    const url = new URL(value)
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null
  } catch { return null }
}
