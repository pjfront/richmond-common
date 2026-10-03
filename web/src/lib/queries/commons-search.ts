import { supabase, RICHMOND_FIPS } from './_shared'
import { searchSite } from './search'
import { getPublicFinanceSnapshot } from './finance-public'
import { filterFinanceEvents } from '../finance-ledger'
import { agendaItemPath } from '../format'
import { readCompleteRecords } from '../complete-record-read'
import { failReadPath } from '../read-path-unavailable'
import { normalizeMotionVotes } from '../vote-records'
import { stageVoteSourceReviewForItem } from '../stage-vote-source-review'
import { COMMONS_PAGE_SIZE, COMMONS_RANKED_LIMIT, matchesCommonsScope, publicSourceUrl } from '../commons-search'
import type { CommonsAgendaRecord, CommonsMotion, CommonsSearchPlan, CommonsSearchResponse } from '../commons-search'
import type { Tables } from '../types'

type AgendaProjection = Pick<Tables<'agenda_items'>, 'id' | 'meeting_id' | 'item_number' | 'title' | 'topic_label' | 'category' | 'created_at' | 'agenda_source_retired_at'> & {
  meetings: Pick<Tables<'meetings'>, 'id' | 'city_fips' | 'meeting_date' | 'agenda_url' | 'minutes_url' | 'video_url' | 'source_cancelled_at'>
}
type MotionProjection = Pick<Tables<'motions'>, 'id' | 'agenda_item_id' | 'motion_text' | 'result' | 'source' | 'sequence_number' | 'created_at'>
type VoteProjection = Pick<Tables<'votes'>, 'id' | 'motion_id' | 'official_id' | 'official_name' | 'vote_choice' | 'source'>
const AGENDA_COLUMNS = 'id,meeting_id,item_number,title,topic_label,category,created_at,agenda_source_retired_at,meetings!inner(id,city_fips,meeting_date,agenda_url,minutes_url,video_url,source_cancelled_at)'
const MOTION_COLUMNS = 'id,agenda_item_id,motion_text,result,source,sequence_number,created_at'
const VOTE_COLUMNS = 'id,motion_id,official_id,official_name,vote_choice,source'

function activeAgendaQuery(votesOnly = false) {
  return supabase.from('agenda_items').select(AGENDA_COLUMNS + (votesOnly ? ',motions!inner(id)' : ''), { count: 'exact' })
    .eq('meetings.city_fips', RICHMOND_FIPS).is('agenda_source_retired_at', null).is('meetings.source_cancelled_at', null)
}

function agendaRecord(row: AgendaProjection, votesOnly: boolean): CommonsAgendaRecord | null {
  if (!row.meetings || row.meetings.id !== row.meeting_id || row.meetings.city_fips !== RICHMOND_FIPS
    || row.agenda_source_retired_at !== null || row.meetings.source_cancelled_at !== null || !row.title || !row.created_at) {
    failReadPath('Commons agenda search', 'Invalid active source identity')
  }
  const review = stageVoteSourceReviewForItem(row)
  const sourceUrl = review?.sourceUrl ?? publicSourceUrl(row.meetings.agenda_url) ?? publicSourceUrl(row.meetings.minutes_url)
  // An old indexed item without a document link cannot be attributed. Withhold
  // that card and disclose the gap instead of blocking correctly sourced cards.
  if (!sourceUrl) return null
  return { kind: votesOnly ? 'votes' : 'agenda', id: row.id, title: row.title, itemNumber: row.item_number,
    meetingDate: row.meetings.meeting_date, topic: row.topic_label, category: row.category,
    url: agendaItemPath(row.meeting_id, row.item_number), sourceUrl,
    minutesUrl: review?.sourceUrl ?? publicSourceUrl(row.meetings.minutes_url), recordingUrl: publicSourceUrl(row.meetings.video_url), indexedAt: row.created_at, motions: [],
    ...(review ? { voteSourceReview: review } : {}) }
}

async function readMotions(itemIds: string[]): Promise<MotionProjection[]> {
  if (!itemIds.length) return []
  const rows = await readCompleteRecords('Commons motion records', (from, to) => supabase.from('motions')
    .select(MOTION_COLUMNS, { count: 'exact' }).in('agenda_item_id', itemIds).order('sequence_number').order('id').range(from, to),
  { maxRows: 1000, maxPages: 10 }) as MotionProjection[]
  if (rows.some(row => !itemIds.includes(row.agenda_item_id))) failReadPath('Commons motion records', 'Motion belongs to another item')
  return rows
}

async function enrichVotes(records: CommonsAgendaRecord[], motions?: MotionProjection[]): Promise<void> {
  const items = new Map(records.filter(record => !record.voteSourceReview).map(record => [record.id, record]))
  const motionRows = motions?.filter(row => items.has(row.agenda_item_id)) ?? await readMotions([...items.keys()])
  if (motionRows.some(row => !items.has(row.agenda_item_id))) failReadPath('Commons motion records', 'Motion belongs to another item')
  const motionIds = new Set(motionRows.map(row => row.id))
  const votes = motionRows.length ? await readCompleteRecords('Commons vote records', (from, to) => supabase.from('votes')
    .select(VOTE_COLUMNS, { count: 'exact' }).in('motion_id', [...motionIds]).order('id').range(from, to),
  { maxRows: 5000, maxPages: 20 }) as VoteProjection[] : []
  if (votes.some(row => !motionIds.has(row.motion_id))) failReadPath('Commons vote records', 'Vote belongs to another motion')
  const byMotion = new Map<string, VoteProjection[]>()
  for (const vote of votes) byMotion.set(vote.motion_id, [...(byMotion.get(vote.motion_id) ?? []), vote])
  for (const motion of motionRows) {
    const detail: CommonsMotion = { id: motion.id, text: motion.motion_text, result: motion.result,
      source: motion.source, indexedAt: motion.created_at,
      votes: normalizeMotionVotes(byMotion.get(motion.id) ?? []).map(vote => ({ id: vote.id, name: vote.official_name, choice: vote.vote_choice, source: vote.source })) }
    items.get(motion.agenda_item_id)!.motions.push(detail)
  }
}

/** Only public read operations; the search_site RPC is STABLE and read-only. */
export async function searchCommons(plan: CommonsSearchPlan): Promise<CommonsSearchResponse> {
  const filters = { q: plan.q, mode: plan.mode, topic: plan.topic, from: plan.from, to: plan.to, page: plan.page }
  const start = (plan.page - 1) * COMMONS_PAGE_SIZE
  if (plan.mode === 'money') {
    const snapshot = await getPublicFinanceSnapshot()
    const lower = (text: string | null) => text?.normalize('NFKC').toLocaleLowerCase('en-US') ?? ''
    const keyword = lower(plan.keywords)
    const matches = filterFinanceEvents(snapshot.events, { q: plan.keywords, activity: plan.contributionsOnly ? 'contributions' : '' })
      .filter(row => (!plan.from || row.activity_date >= plan.from) && (!plan.to || row.activity_date <= plan.to))
      .filter(row => !plan.moneyRole || lower(plan.moneyRole === 'recipient' ? row.recipient_name : row.donor_name).includes(keyword))
    const shown = matches.slice(start, start + COMMONS_PAGE_SIZE)
    if (shown.some(row => !publicSourceUrl(row.source_url) || row.source_urls.some(url => !publicSourceUrl(url)))) {
      failReadPath('Commons money search', 'Invalid original filing link')
    }
    return { filters, interpretation: plan.interpretation, records: shown.map(event => ({ kind: 'money', id: event.event_key, event })),
      topics: [], hasMore: start + shown.length < matches.length && plan.page < 100, total: matches.length,
      limited: snapshot.truncated, coverage: snapshot.coverage,
      limitations: ['Money searches use the published 2026 filing index. Missing results do not establish that no activity occurred.',
        'Names are matched as reported; this search does not resolve similarly named people or establish influence.',
        ...(snapshot.truncated ? ['The source projection reached its 5,000-record bound; results cover that limited set.'] : [])] }
  }

  let rows: AgendaProjection[]
  let hasMore: boolean
  let total: number | null
  let allMotions: MotionProjection[] | undefined
  const limitations: string[] = []
  let topics: string[]
  if (plan.keywords) {
    // Two bounded pages per content type. Never label this ranked window complete.
    const agendaPages = await Promise.all([0, 50].map(offset => searchSite(plan.keywords, { resultType: 'agenda_item', limit: 50, offset })))
    const hits = agendaPages.flat()
    let orderedIds = [...new Set(hits.map(hit => hit.id))]
    if (plan.mode === 'votes') {
      const motionPages = await Promise.all([0, 50].map(offset => searchSite(plan.keywords, { resultType: 'vote_explainer', limit: 50, offset })))
      const motionIds = [...new Set(motionPages.flat().map(hit => hit.id))]
      if (motionIds.length) {
        const linked = await readCompleteRecords('Commons matched motion links', (from, to) => supabase.from('motions')
          .select('id,agenda_item_id', { count: 'exact' }).in('id', motionIds).order('id').range(from, to), { maxRows: 200, maxPages: 4 })
        if (linked.some(row => !motionIds.includes(row.id))) failReadPath('Commons matched motion links', 'Unexpected matched motion')
        orderedIds = [...new Set([...orderedIds, ...linked.map(row => row.agenda_item_id)])]
      }
    }
    const projected = orderedIds.length ? await readCompleteRecords('Commons ranked agenda sources', (from, to) => activeAgendaQuery()
      .in('id', orderedIds).order('id').range(from, to).returns<AgendaProjection[]>(), { maxRows: 200, maxPages: 4 }) : []
    const byId = new Map(projected.map(row => [row.id, row]))
    if (projected.length !== orderedIds.length || projected.some(row => !orderedIds.includes(row.id))) {
      failReadPath('Commons ranked agenda sources', 'The matched source set changed')
    }
    rows = orderedIds.map(id => byId.get(id)!)
    topics = [...new Set(rows.flatMap(row => row.topic_label ? [row.topic_label] : []))].sort()
    rows = rows.filter(row => matchesCommonsScope({ topic: row.topic_label, meetingDate: row.meetings.meeting_date }, plan))
    if (plan.mode === 'votes') {
      allMotions = await readMotions(rows.filter(row => !stageVoteSourceReviewForItem(row)).map(row => row.id))
      const withMotions = new Set(allMotions.map(row => row.agenda_item_id))
      rows = rows.filter(row => withMotions.has(row.id) || stageVoteSourceReviewForItem(row))
    }
    total = rows.length
    hasMore = start + COMMONS_PAGE_SIZE < rows.length
    rows = rows.slice(start, start + COMMONS_PAGE_SIZE)
    limitations.push(`Keyword search checks up to ${COMMONS_RANKED_LIMIT} ranked agenda matches${plan.mode === 'votes' ? ' plus 100 matched vote explanations' : ''}. Tags and dates narrow that retrieved set; it is not a complete history.`)
  } else {
    rows = []
    total = null
    const seen = new Set<string>()
    // A lower HTTP row cap is not the end of a page. Advance by actual rows,
    // keeping one exact count across these bounded reads.
    for (let attempt = 0; attempt < COMMONS_PAGE_SIZE; attempt++) {
      let query = activeAgendaQuery(plan.mode === 'votes')
      if (plan.topic) query = query.eq('topic_label', plan.topic)
      if (plan.from) query = query.gte('meetings.meeting_date', plan.from)
      if (plan.to) query = query.lte('meetings.meeting_date', plan.to)
      const offset = start + rows.length
      const { data, error, count } = await query.order('meetings(meeting_date)', { ascending: false }).order('id').range(offset, start + COMMONS_PAGE_SIZE - 1).returns<AgendaProjection[]>()
      if (error || !data || count == null || !Number.isSafeInteger(count) || count < 0 || (total !== null && total !== count)) {
        failReadPath('Commons agenda browse', error ?? 'The result count is unavailable or changed')
      }
      if (data.length > COMMONS_PAGE_SIZE - rows.length || (!data.length && offset < count)) failReadPath('Commons agenda browse', 'Incomplete result page')
      total = count
      for (const row of data) {
        if (!row.id || seen.has(row.id)) failReadPath('Commons agenda browse', 'Repeated or missing item identity')
        seen.add(row.id)
        rows.push(row)
      }
      if (rows.length === COMMONS_PAGE_SIZE || start + rows.length >= count) break
    }
    if (rows.length < COMMONS_PAGE_SIZE && start + rows.length < (total ?? 0)) failReadPath('Commons agenda browse', 'Result page exceeded its read bound')
    hasMore = start + rows.length < (total ?? 0) && plan.page < 100
    topics = [...new Set(rows.flatMap(row => row.topic_label ? [row.topic_label] : []))].sort()
    limitations.push('Browsing shows indexed, active agenda records. Source coverage may vary by meeting.')
    if ((total ?? 0) > 2000) limitations.push('Browsing is limited to the first 2,000 matching items; narrow the date range or tag to reach older records.')
  }
  const records = rows.map(row => agendaRecord(row, plan.mode === 'votes')).filter((row): row is CommonsAgendaRecord => row !== null)
  if (records.length !== rows.length) {
    limitations.push('Some retrieved items are withheld because an original meeting document link is unavailable.')
    total = null
  }
  if (records.some(record => record.voteSourceReview)) {
    limitations.push('Motion and vote records for a retrieved item are held for source review because they conflict with its original minutes. The item and source document remain available.')
    if (plan.mode === 'votes') total = null
  }
  if (plan.mode === 'votes') await enrichVotes(records, allMotions)
  return { filters, interpretation: plan.interpretation, records, topics, hasMore, total,
    limited: !!plan.keywords || (total ?? 0) > 2000, limitations, coverage: [] }
}
