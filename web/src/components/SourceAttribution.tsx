/**
 * Source attribution rendering for auto-generated text artifacts.
 *
 * Single source of truth for the "Auto-summarized from X" labels that
 * previously lived as fixed strings scattered across components. Every
 * artifact-rendering site reads its sibling Provenance struct (written
 * by the Python generator in the same UPDATE) and passes it here.
 *
 * Design rationale: Entry 51 in JOURNAL.md, audit 2026-04-27. Provenance
 * is a property of the artifact, not the renderer — so the label cannot
 * desync from reality if both live in the same row write.
 *
 * Public-facing wording is a judgment call (see judgment-boundaries.md).
 * Strings here were lifted from previously-shipped fixed strings; changes
 * need operator review.
 */

import type { Provenance } from '@/lib/types'

const KCRT_URL = 'https://www.ci.richmond.ca.us/1604/KCRT-702'

// ── Primitive: just the source phrase, hyperlinked when URL present ───

/**
 * Renders the source phrase only ("official minutes", "KCRT meeting
 * recording", etc.). For composing into surrounding sentences. When the
 * provenance carries a URL, the phrase becomes a link.
 */
export function SourceLabel({ p }: { p: Provenance }) {
  switch (p.kind) {
    case 'official_minutes':
      return p.minutes_url ? (
        <a
          href={p.minutes_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-civic-navy-light hover:text-civic-navy hover:underline"
        >
          official minutes
        </a>
      ) : (
        <>official minutes</>
      )
    case 'meeting_recording':
      return p.channel === 'kcrt' ? (
        <a
          href={KCRT_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="text-civic-navy-light hover:text-civic-navy hover:underline"
        >
          KCRT meeting recording
        </a>
      ) : (
        <>meeting recording</>
      )
    case 'agenda_packet':
      return p.agenda_url ? (
        <a
          href={p.agenda_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-civic-navy-light hover:text-civic-navy hover:underline"
        >
          official agenda packet
        </a>
      ) : (
        <>official agenda packet</>
      )
    case 'mixed':
      return <>official minutes and recent meeting recordings</>
    case 'campaign_filing_period':
      return (
        <a
          href="https://public.netfile.com/pub2/?AID=RICH"
          target="_blank"
          rel="noopener noreferrer"
          className="text-civic-navy-light hover:text-civic-navy hover:underline"
        >
          NetFile + extracted paper filings
        </a>
      )
  }
}

// ── Compositions: one wrapper per render context ──────────────────────

/**
 * Footer for meeting_recap and meeting_summary (MeetingNarrative cases
 * 1, 2b, 3). Replaces the four fixed-string variants previously copied
 * around the component. Renders nothing when provenance is null —
 * backfill will fill it in; better to omit attribution than to lie.
 */
export function RecapAttribution({ p }: { p: Provenance | null }) {
  if (!p) return null
  switch (p.kind) {
    case 'official_minutes':
      return (
        <>
          Auto-summarized from <SourceLabel p={p} /> and vote records
        </>
      )
    case 'meeting_recording':
      return (
        <>
          Auto-summarized from the <SourceLabel p={p} />. Vote outcomes are
          preliminary until the City Clerk publishes official minutes (4-6 weeks).
        </>
      )
    case 'agenda_packet':
      // Unusual for a recap; defensive — renders coherently if it ever happens.
      return (
        <>
          Auto-summarized from the <SourceLabel p={p} />
        </>
      )
    case 'mixed':
      return (
        <>
          Auto-summarized from official minutes plus {p.from_transcript} additional
          vote{p.from_transcript === 1 ? '' : 's'} extracted from the meeting
          recording while minutes are pending.
        </>
      )
    case 'campaign_filing_period':
      // Recap attribution should never get a campaign briefing provenance;
      // render nothing rather than lying about the source.
      return null
  }
}

/**
 * Footer for orientation_preview (MeetingNarrative case 4 + the
 * collapsible orientation block under recap). Always agenda_packet
 * kind. Defensive null fallback — render nothing rather than lying.
 */
export function OrientationAttribution({ p }: { p: Provenance | null }) {
  if (!p || p.kind === 'campaign_filing_period') return null
  return (
    <>
      Auto-summarized from the <SourceLabel p={p} />
    </>
  )
}

/**
 * Footer for plain_language_summary (AgendaItemCard inline summary).
 * Always agenda_packet kind. Phrasing differs from recap — plain
 * language summaries describe the situation, not the vote.
 */
export function PlainLanguageAttribution({ p }: { p: Provenance | null }) {
  // Pre-backfill fallback matches the prior shipped string verbatim, so
  // there's no visual flicker when provenance is missing.
  if (!p || p.kind === 'agenda_packet') {
    return <>Auto-generated summary. Source: official agenda documents.</>
  }
  return (
    <>
      Auto-generated summary. Source: <SourceLabel p={p} />.
    </>
  )
}

/**
 * Footer for theme groupings (AgendaItemCard InlineThemes,
 * CommunityVoiceSection, VotedItemCard). The provenance here describes
 * the public_comments source that fed the theme extraction — derived at
 * query time from public_comments.source, not stored on the item.
 */
export function ThemeAttribution({ p }: { p: Provenance | null }) {
  // Null falls back to a deliberately vague catch-all, matching the
  // pre-audit default behavior.
  if (!p) {
    return <>Theme groupings and summaries are auto-generated from meeting records.</>
  }
  return (
    <>
      Theme groupings and summaries are auto-generated from <SourceLabel p={p} />.
    </>
  )
}

/**
 * Footer for BioSummary. Multi-sentence, includes officialName and
 * meetingCount in surrounding text. The 'mixed' kind is the audit's
 * highest-stakes new disclosure (Entry 51 #5): bios that include
 * transcript-extracted votes must say so.
 */
export function BioAttribution({
  p,
  officialName,
  meetingCount,
  generatedAt,
}: {
  p: Provenance | null
  officialName: string
  meetingCount: number
  generatedAt: string | null
}) {
  const lastUpdated = generatedAt ? (
    <>
      <br />
      Last updated: {new Date(generatedAt).toLocaleDateString()}
    </>
  ) : null

  // Pre-provenance fallback: matches the prior shipped string. Will
  // disappear once the bio backfill completes.
  if (!p) {
    return (
      <>
        This summary was auto-generated based on {officialName}&apos;s voting record
        across {meetingCount} meetings. It reflects patterns in official vote data,
        not editorial judgment.
        <br />
        Data sources: City of Richmond certified meeting minutes
        {lastUpdated}
      </>
    )
  }

  switch (p.kind) {
    case 'official_minutes':
      return (
        <>
          This summary was auto-generated based on {officialName}&apos;s voting
          record across {meetingCount} meetings. It reflects patterns in official
          vote data, not editorial judgment.
          <br />
          Data sources: City of Richmond certified meeting minutes
          {lastUpdated}
        </>
      )
    case 'mixed':
      return (
        <>
          This summary was auto-generated based on {officialName}&apos;s voting
          record across {meetingCount} meetings. It reflects patterns in vote
          data, not editorial judgment.
          <br />
          Data sources: {p.from_minutes} votes from official City of Richmond
          minutes, plus {p.from_transcript} from auto-caption transcripts of
          recent meetings (used until minutes are published, typically 4-6 weeks).
          {lastUpdated}
        </>
      )
    case 'meeting_recording':
      // Edge case: bio derived only from transcripts (e.g., a brand-new
      // member with no minutes-source votes yet). Be explicit.
      return (
        <>
          This summary was auto-generated based on {officialName}&apos;s voting
          record across {meetingCount} meetings, derived entirely from
          auto-caption transcripts of recent meetings. Vote tallies may revise
          as official minutes are published.
          {lastUpdated}
        </>
      )
    case 'agenda_packet':
      // Should never happen for a bio. Defensive fallback.
      return (
        <>
          This summary was auto-generated based on {officialName}&apos;s record
          across {meetingCount} meetings.
          {lastUpdated}
        </>
      )
    case 'campaign_filing_period':
      // Bios should never carry a campaign-filing provenance. Defensive
      // fallback — render the generic minutes-source disclosure rather
      // than misattribute to filing data.
      return (
        <>
          This summary was auto-generated based on {officialName}&apos;s record
          across {meetingCount} meetings.
          {lastUpdated}
        </>
      )
  }
}


/**
 * Footer for the per-candidate filing-period briefing sections (F1–F4)
 * on the candidate detail page. The briefing is a structured snapshot
 * of one filing period — totals reconcile to filings closed on
 * `period_end`, not to live database state, so we surface period_label
 * + filed_through to make the snapshot semantics clear.
 */
export function BriefingAttribution({ p }: { p: Provenance | null }) {
  if (!p || p.kind !== 'campaign_filing_period') return null
  const filedThrough = p.filed_through
    ? new Date(p.filed_through + 'T00:00:00').toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : null
  const generated = new Date(p.as_of).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
  return (
    <>
      Auto-generated from <SourceLabel p={p} /> for the{' '}
      <strong>{p.period_label}</strong> filing period
      {filedThrough && <> (last filing dated {filedThrough})</>}. Based on{' '}
      {p.contributions_count.toLocaleString()} contribution
      {p.contributions_count === 1 ? '' : 's'}
      {p.paper_filings_count > 0
        ? ` plus ${p.paper_filings_count} extracted paper filing${p.paper_filings_count === 1 ? '' : 's'}`
        : ''}
      . Briefing generated {generated}.
    </>
  )
}
