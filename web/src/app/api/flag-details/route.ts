import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'


const RICHMOND_FIPS = '0660620'
const CONFIDENCE_PUBLISHED = 0.5

/**
 * GET /api/flag-details?id=<flag_id>
 *   Returns description + evidence for a single flag (on-demand expand).
 *
 * GET /api/flag-details?all=1
 *   Returns all published flags as lightweight rows (no description/evidence).
 *   Used by the client-side table to avoid a 167KB RSC payload.
 */
export async function GET(request: NextRequest) {
  const flagId = request.nextUrl.searchParams.get('id')
  const all = request.nextUrl.searchParams.get('all')

  // Single flag detail
  if (flagId) {
    const { data, error } = await supabase
      .from('conflict_flags')
      .select('description, evidence, confidence_factors, scanner_version')
      .eq('id', flagId)
      .eq('city_fips', RICHMOND_FIPS)
      .single()

    if (error) return NextResponse.json({ error: error.message }, { status: 500 })
    if (!data) return NextResponse.json({ error: 'Flag not found' }, { status: 404 })

    return NextResponse.json({
      description: data.description,
      evidence: data.evidence,
      confidence_factors: data.confidence_factors,
      scanner_version: data.scanner_version,
    })
  }

  // All published flags (lightweight)
  if (all) {
    const { data: flags, error } = await supabase
      .from('conflict_flags')
      .select(`
        id, flag_type, confidence,
        meeting_id, agenda_item_id, official_id,
        meetings!inner(meeting_date),
        agenda_items!inner(title, item_number, category),
        officials!inner(name)
      `)
      .eq('city_fips', RICHMOND_FIPS)
      .eq('is_current', true)
      .gte('confidence', CONFIDENCE_PUBLISHED)
      .order('confidence', { ascending: false })
      .limit(1000)

    if (error) return NextResponse.json({ error: error.message }, { status: 500 })
    if (!flags) return NextResponse.json([])

    // Batch-fetch votes for all flagged agenda items
    const agendaItemIds = [...new Set(flags.map((f) => f.agenda_item_id).filter(Boolean))]
    const officialIds = [...new Set(flags.map((f) => f.official_id).filter(Boolean))]

    type MotionVoteRow = {
      agenda_item_id: string
      result: string
      vote_tally: string | null
      votes: Array<{ official_id: string; vote_choice: string }> | null
    }
    const allMotionVotes: MotionVoteRow[] = []
    for (let i = 0; i < agendaItemIds.length; i += 200) {
      const batch = agendaItemIds.slice(i, i + 200)
      // Left join (no !inner) so motions are returned even when no individual
      // vote record matches the flagged official.  The .in filter on a left
      // join narrows the nested votes array without dropping the parent row.
      const { data: mvBatch } = await supabase
        .from('motions')
        .select('agenda_item_id, result, vote_tally, votes(official_id, vote_choice)')
        .in('agenda_item_id', batch)
        .in('votes.official_id', officialIds)
      if (mvBatch) allMotionVotes.push(...(mvBatch as unknown as MotionVoteRow[]))
    }

    // Build vote lookup: (agenda_item_id, official_id) → vote data
    const voteMap = new Map<string, { vote_choice: string | null; motion_result: string; is_unanimous: boolean | null }>()
    for (const m of allMotionVotes) {
      const votes = (m.votes ?? []) as Array<{ official_id: string; vote_choice: string }>
      const nays = votes.filter(v => v.vote_choice === 'nay').length
      const ayes = votes.filter(v => v.vote_choice === 'aye').length
      const is_unanimous = votes.length > 0 ? (nays === 0 || ayes === 0) : null
      if (votes.length > 0) {
        for (const v of votes) {
          const key = `${m.agenda_item_id}::${v.official_id}`
          if (!voteMap.has(key)) {
            voteMap.set(key, { vote_choice: v.vote_choice, motion_result: m.result, is_unanimous })
          }
        }
      } else {
        // Motion exists but no individual vote record for these officials.
        // Store motion-level data so the UI can at least show the result.
        for (const oid of officialIds) {
          const key = `${m.agenda_item_id}::${oid}`
          if (!voteMap.has(key)) {
            voteMap.set(key, { vote_choice: null, motion_result: m.result, is_unanimous })
          }
        }
      }
    }

    // Build lightweight rows with joined fields flattened
    const rows = flags.map((f) => {
      const meeting = f.meetings as unknown as { meeting_date: string }
      const item = f.agenda_items as unknown as { title: string; item_number: string; category: string | null }
      const official = f.officials as unknown as { name: string }
      const slug = official.name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '')
      const vote = voteMap.get(`${f.agenda_item_id}::${f.official_id}`)

      return {
        id: f.id,
        flag_type: f.flag_type,
        confidence: f.confidence,
        meeting_id: f.meeting_id,
        meeting_date: meeting.meeting_date,
        agenda_item_id: f.agenda_item_id,
        agenda_item_title: item.title,
        agenda_item_number: item.item_number,
        agenda_item_category: item.category,
        official_name: official.name,
        official_slug: slug,
        official_id: f.official_id,
        vote_choice: vote?.vote_choice ?? null,
        motion_result: vote?.motion_result ?? null,
        is_unanimous: vote?.is_unanimous ?? null,
      }
    })

    return NextResponse.json(rows, {
      headers: { 'Cache-Control': 'public, s-maxage=3600, stale-while-revalidate=86400' },
    })
  }

  return NextResponse.json({ error: 'Missing id or all parameter' }, { status: 400 })
}
