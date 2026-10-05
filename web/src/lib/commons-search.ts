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
  voteSourceReview?: import('./stage-vote-source-review').StageVoteSourceReview
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

/** A bounded record-retrieval grammar. Unrecognized questions remain keywords. */
export function planCommonsSearch(params: URLSearchParams): CommonsSearchPlan {
  const q = (params.get('q') ?? '').normalize('NFKC').trim()
  if (q.length > 200) throw new CommonsSearchInputError('Use a search of 200 characters or fewer.')
  const text = q.replace(/[?]+$/, '').replace(/^(?:show(?:\s+me)?|find(?:\s+me)?|list)\s+/i, '').trim()
  // Native Auto forms may send mode=""; the API still returns a resolved mode.
  const rawMode = params.get('mode') || params.get('type') || null
  if (rawMode && !['agenda', 'votes', 'money'].includes(rawMode)) {
    throw new CommonsSearchInputError('Choose agenda items, votes, or money.')
  }
  const mode: CommonsMode = rawMode as CommonsMode | null
    ?? (/^(?:donations?|contributions?)\b|^who\s+(?:donated|contributed)\s+to\b/i.test(text) ? 'money' : /^who\s+voted\s+on\b/i.test(text) ? 'votes' : 'agenda')
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
  const year = text.match(/\s+(?:in|during)\s+(20\d{2})$/i)
  const scopedText = year ? text.slice(0, year.index).trim() : text
  const moneyPhrase = scopedText.match(/^(?:donations?|contributions?)\s+(to|from)\s+(.+)$/i)
  const donorQuestion = scopedText.match(/^who\s+(?:donated|contributed)\s+to\s+(.+)$/i)
  const voteQuestion = scopedText.match(/^who\s+voted\s+on\s+(.+)$/i)
  const agendaQuestion = scopedText.match(/^what\s+(.+?)\s+(?:agenda items?|decisions?)(?:\s+were\s+made)?$/i)
    ?? scopedText.match(/^what\s+decisions?\s+were\s+made\s+(?:about|on)\s+(.+)$/i)
  const agendaPhrase = scopedText.match(/^(.+?)\s+(?:agenda items?|decisions?)$/i)
  const question = /^(?:who|what|why|how|did|does|do|was|were|is|are|can|could|should|would)\b/i.test(scopedText)
  // A single target and one calendar year are supported. Leave compound roles,
  // relative/range dates, tally/causal clauses and vote-choice requests literal.
  const compoundMoneyRole = moneyPhrase
    ? moneyPhrase[1].toLowerCase() === 'to' ? /\s+from\s+/i.test(moneyPhrase[2]) : /\s+to\s+(?!elect\b)/i.test(moneyPhrase[2])
    : !!donorQuestion && /\s+from\s+/i.test(donorQuestion[1])
  const unsupportedClause = compoundMoneyRole || /\b(?:why|how|because|that|which|whose|totals?|sums?|tall(?:y|ies)|caused|influenced|changed|affected)\b|\b(?:and|or)\s+(?:to|from|who|what|why|how|did|does)\b|\b(?:over|under|above|below|more than|less than|at least)\s*\$?\d/i.test(scopedText)
    || !!voteQuestion && /\bagainst\b|\bin favor of\b/i.test(voteQuestion[1])
  const unsupportedTime = /\b(?:in|during|between|since|before|after|through|until)\s+(?:20\d{2}|last|this|next)\b|\bfrom\s+20\d{2}\s+to\s+20\d{2}\b|\b(?:last|this|next)\s+(?:year|month|week)\b/i.test(scopedText)
  const supportedQuestion = !!donorQuestion || !!voteQuestion || !!agendaQuestion
  const canInterpret = !unsupportedClause && !unsupportedTime && (!question || supportedQuestion)
  let keywords = text
  let moneyRole: CommonsSearchPlan['moneyRole'] = ''
  let contributionsOnly = false
  let keywordFallback = !canInterpret
  let modeOverride = ''
  if (canInterpret) {
    keywords = scopedText
    if (year) {
      if (!from) from = `${year[1]}-01-01`
      if (!to) to = `${year[1]}-12-31`
    }
    if (mode === 'money' && (moneyPhrase || donorQuestion)) {
      moneyRole = donorQuestion || moneyPhrase![1].toLowerCase() === 'to' ? 'recipient' : 'source'
      contributionsOnly = true
      keywords = (donorQuestion?.[1] ?? moneyPhrase![2]).trim()
    } else if (mode !== 'money' && (voteQuestion || agendaQuestion || agendaPhrase)) {
      keywords = (voteQuestion?.[1] ?? agendaQuestion?.[1] ?? agendaPhrase![1]).trim()
      if (rawMode === 'agenda' && voteQuestion) modeOverride = 'Selected agenda mode; retrieving matching items rather than roll-call records'
      if (rawMode === 'votes' && (agendaQuestion || agendaPhrase)) modeOverride = 'Selected votes mode; retrieving motions on matching items'
    } else if (moneyPhrase || donorQuestion || voteQuestion || agendaQuestion) {
      keywordFallback = true
      modeOverride = `Selected ${mode} mode; question wording is searched as keywords`
    }
  }
  if (from && to && from > to) throw new CommonsSearchInputError('The start date must come before the end date.')
  const recordKind = { agenda: 'Agenda items', votes: 'Recorded votes', money: 'Campaign money' }[mode]
  const interpretation = [`Records: ${recordKind}`, keywords ? `Keywords: ${keywords}` : 'Browse indexed records']
  if (modeOverride) interpretation.push(modeOverride)
  if (keywordFallback) interpretation.push('Keyword search only; this question is not answered')
  if (moneyRole) interpretation.push(`${moneyRole === 'recipient' ? 'Recipient' : 'Contributor'} name contains: ${keywords}`)
  if (contributionsOnly) interpretation.push('Cash contribution records')
  if (topic) interpretation.push(`Tag: ${topic}`)
  if (from || to) interpretation.push(`${mode === 'money' ? 'Activity' : 'Meeting'} dates: ${from || 'any start'} to ${to || 'any end'}`)
  if (year && (params.get('from') && params.get('from') !== `${year[1]}-01-01`
    || params.get('to') && params.get('to') !== `${year[1]}-12-31`)) {
    interpretation.push('Explicit date filters take precedence over the year in the question')
  }
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
