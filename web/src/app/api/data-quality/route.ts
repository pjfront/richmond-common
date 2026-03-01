import { NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import type {
  DataSourceFreshness,
  MeetingCompleteness,
  DataAnomaly,
  DataQualityResponse,
} from '@/lib/types'

const RICHMOND_FIPS = '0660620'
const RECENT_MEETING_LIMIT = 10
const ANOMALY_STDDEV_THRESHOLD = 2.0

// Staleness thresholds (same as /api/data-freshness)
const FRESHNESS_THRESHOLDS: Record<string, number> = {
  netfile: 14,
  calaccess: 45,
  escribemeetings: 7,
  archive_center: 60,
  nextrequest: 7,
  socrata_payroll: 45,
  socrata_expenditures: 45,
}

export async function GET() {
  try {
    // Run all queries in parallel
    const [freshnessResult, meetingsResult, statsResult] = await Promise.all([
      // 1. Source freshness (reuses data-freshness logic)
      supabase
        .from('data_sync_log')
        .select('source, completed_at')
        .eq('city_fips', RICHMOND_FIPS)
        .eq('status', 'completed')
        .order('completed_at', { ascending: false }),

      // 2. Recent meetings with counts via separate queries
      supabase
        .from('meetings')
        .select('id, meeting_date, meeting_type, minutes_url, agenda_url, video_url')
        .eq('city_fips', RICHMOND_FIPS)
        .order('meeting_date', { ascending: false })
        .limit(RECENT_MEETING_LIMIT),

      // 3. Overall meeting count + document coverage
      supabase.rpc('get_meeting_coverage_stats', { p_city_fips: RICHMOND_FIPS }),
    ])

    // Build freshness
    const freshness = buildFreshness(freshnessResult.data ?? [])

    // Build meeting completeness (need counts per meeting)
    const meetings = meetingsResult.data ?? []
    const meetingIds = meetings.map((m) => m.id)

    // Get counts for these meetings in parallel
    const [itemCounts, voteCounts, attendanceCounts] = await Promise.all([
      getItemCounts(meetingIds),
      getVoteCounts(meetingIds),
      getAttendanceCounts(meetingIds),
    ])

    const recentMeetings: MeetingCompleteness[] = meetings.map((m) => {
      const itemCount = itemCounts.get(m.id) ?? 0
      const voteCount = voteCounts.get(m.id) ?? 0
      const attendanceCount = attendanceCounts.get(m.id) ?? 0
      const hasMinutes = !!m.minutes_url
      const hasAgenda = !!m.agenda_url
      const hasVideo = !!m.video_url

      let score = 0
      if (itemCount > 0) score += 30
      if (voteCount > 0) score += 30
      if (attendanceCount > 0) score += 20
      const urlScore = [hasMinutes, hasAgenda, hasVideo].filter(Boolean).length / 3
      score += Math.floor(20 * urlScore)

      return {
        meeting_id: m.id,
        meeting_date: m.meeting_date,
        meeting_type: m.meeting_type,
        agenda_item_count: itemCount,
        vote_count: voteCount,
        attendance_count: attendanceCount,
        has_minutes: hasMinutes,
        has_agenda: hasAgenda,
        has_video: hasVideo,
        completeness_score: score,
      }
    })

    // Document coverage from RPC or fallback computation
    const coverageData = statsResult.data
    const documentCoverage = buildDocumentCoverage(coverageData, meetings)

    // Compute anomalies from the recent meetings
    const anomalies = await computeAnomalies(recentMeetings)

    // Derive overall status
    const staleCount = freshness.filter((f) => f.is_stale).length
    const alertCount = anomalies.filter((a) => a.severity === 'alert').length
    const warningCount = anomalies.filter((a) => a.severity === 'warning').length

    let overallStatus: 'healthy' | 'warning' | 'alert' = 'healthy'
    if (alertCount > 0 || staleCount > 2) {
      overallStatus = 'alert'
    } else if (warningCount > 0 || staleCount > 0) {
      overallStatus = 'warning'
    }

    const completeCount = recentMeetings.filter(
      (m) => m.agenda_item_count > 0 && m.vote_count > 0 && m.attendance_count > 0,
    ).length

    const response: DataQualityResponse = {
      freshness: {
        sources: freshness,
        stale_count: staleCount,
        total: freshness.length,
      },
      completeness: {
        total_meetings: documentCoverage.total,
        complete_meetings: completeCount,
        document_coverage: {
          minutes: documentCoverage.minutes,
          agenda: documentCoverage.agenda,
          video: documentCoverage.video,
        },
        recent_meetings: recentMeetings,
      },
      anomalies,
      overall_status: overallStatus,
      checked_at: new Date().toISOString(),
    }

    return NextResponse.json(response, {
      headers: {
        'Cache-Control': 'public, s-maxage=3600, stale-while-revalidate=7200',
      },
    })
  } catch (err) {
    console.error('Data quality check failed:', err)
    return NextResponse.json(
      { error: 'Failed to compute data quality metrics' },
      { status: 500 },
    )
  }
}

// -- Helpers ----------------------------------------------------------------

function buildFreshness(
  rows: { source: string; completed_at: string }[],
): DataSourceFreshness[] {
  const syncMap = new Map<string, string>()
  for (const row of rows) {
    if (row.source && row.completed_at && !syncMap.has(row.source)) {
      syncMap.set(row.source, row.completed_at)
    }
  }

  const now = Date.now()
  return Object.entries(FRESHNESS_THRESHOLDS).map(([source, thresholdDays]) => {
    const lastSync = syncMap.get(source) ?? null
    if (lastSync) {
      const daysSince = (now - new Date(lastSync).getTime()) / (1000 * 60 * 60 * 24)
      return {
        source,
        last_sync: lastSync,
        threshold_days: thresholdDays,
        days_since_sync: Math.round(daysSince * 10) / 10,
        is_stale: daysSince > thresholdDays,
      }
    }
    return {
      source,
      last_sync: null,
      threshold_days: thresholdDays,
      days_since_sync: null,
      is_stale: true,
    }
  })
}

async function getItemCounts(meetingIds: string[]): Promise<Map<string, number>> {
  if (meetingIds.length === 0) return new Map()
  const { data } = await supabase
    .from('agenda_items')
    .select('meeting_id')
    .in('meeting_id', meetingIds)
  const counts = new Map<string, number>()
  for (const row of data ?? []) {
    counts.set(row.meeting_id, (counts.get(row.meeting_id) ?? 0) + 1)
  }
  return counts
}

async function getVoteCounts(meetingIds: string[]): Promise<Map<string, number>> {
  if (meetingIds.length === 0) return new Map()
  // votes -> motions -> agenda_items -> meeting_id
  // Supabase foreign key traversal: votes.motion_id -> motions.agenda_item_id -> agenda_items.meeting_id
  const { data } = await supabase
    .from('votes')
    .select('motion_id, motions!inner(agenda_item_id, agenda_items!inner(meeting_id))')
    .filter('motions.agenda_items.meeting_id', 'in', `(${meetingIds.join(',')})`)

  const counts = new Map<string, number>()
  for (const row of data ?? []) {
    // Supabase returns nested joins as arrays
    const r = row as unknown as {
      motions: Array<{ agenda_items: Array<{ meeting_id: string }> }>
    }
    const mid = r.motions?.[0]?.agenda_items?.[0]?.meeting_id
    if (mid) {
      counts.set(mid, (counts.get(mid) ?? 0) + 1)
    }
  }
  return counts
}

async function getAttendanceCounts(meetingIds: string[]): Promise<Map<string, number>> {
  if (meetingIds.length === 0) return new Map()
  const { data } = await supabase
    .from('meeting_attendance')
    .select('meeting_id')
    .in('meeting_id', meetingIds)
  const counts = new Map<string, number>()
  for (const row of data ?? []) {
    counts.set(row.meeting_id, (counts.get(row.meeting_id) ?? 0) + 1)
  }
  return counts
}

function buildDocumentCoverage(
  rpcData: unknown,
  fallbackMeetings: Array<{ minutes_url: string | null; agenda_url: string | null; video_url: string | null }>,
) {
  // If the RPC exists and returned data, use it
  if (rpcData && Array.isArray(rpcData) && rpcData.length > 0) {
    const row = rpcData[0] as {
      total: number
      has_minutes: number
      has_agenda: number
      has_video: number
    }
    const total = row.total || 0
    return {
      total,
      minutes: { count: row.has_minutes, percentage: total > 0 ? Math.round((row.has_minutes / total) * 1000) / 10 : 0 },
      agenda: { count: row.has_agenda, percentage: total > 0 ? Math.round((row.has_agenda / total) * 1000) / 10 : 0 },
      video: { count: row.has_video, percentage: total > 0 ? Math.round((row.has_video / total) * 1000) / 10 : 0 },
    }
  }

  // Fallback: compute from the meetings we already fetched (limited sample)
  const total = fallbackMeetings.length
  const minutes = fallbackMeetings.filter((m) => m.minutes_url).length
  const agenda = fallbackMeetings.filter((m) => m.agenda_url).length
  const video = fallbackMeetings.filter((m) => m.video_url).length

  return {
    total,
    minutes: { count: minutes, percentage: total > 0 ? Math.round((minutes / total) * 1000) / 10 : 0 },
    agenda: { count: agenda, percentage: total > 0 ? Math.round((agenda / total) * 1000) / 10 : 0 },
    video: { count: video, percentage: total > 0 ? Math.round((video / total) * 1000) / 10 : 0 },
  }
}

async function computeAnomalies(
  recentMeetings: MeetingCompleteness[],
): Promise<DataAnomaly[]> {
  // Get historical baseline for regular meetings
  const { data: allMeetings } = await supabase
    .from('meetings')
    .select('id, meeting_type')
    .eq('city_fips', RICHMOND_FIPS)
    .eq('meeting_type', 'regular')

  if (!allMeetings || allMeetings.length < 3) return []

  const regularIds = allMeetings.map((m) => m.id)

  // Get item counts for all regular meetings
  const { data: allItems } = await supabase
    .from('agenda_items')
    .select('meeting_id')
    .in('meeting_id', regularIds)

  const itemCountMap = new Map<string, number>()
  for (const row of allItems ?? []) {
    itemCountMap.set(row.meeting_id, (itemCountMap.get(row.meeting_id) ?? 0) + 1)
  }

  const itemCounts = regularIds.map((id) => itemCountMap.get(id) ?? 0)
  const avgItems = itemCounts.reduce((a, b) => a + b, 0) / itemCounts.length
  const stddevItems = Math.sqrt(
    itemCounts.reduce((sum, c) => sum + Math.pow(c - avgItems, 2), 0) / itemCounts.length,
  )

  const anomalies: DataAnomaly[] = []
  const threshold = ANOMALY_STDDEV_THRESHOLD

  for (const m of recentMeetings) {
    // Item count anomalies (regular meetings only)
    if (m.meeting_type === 'regular' && stddevItems > 0) {
      if (Math.abs(m.agenda_item_count - avgItems) > threshold * stddevItems) {
        const direction = m.agenda_item_count < avgItems ? 'low' : 'high'
        anomalies.push({
          meeting_id: m.meeting_id,
          meeting_date: m.meeting_date,
          anomaly_type: `${direction}_item_count`,
          description: `${m.agenda_item_count} agenda items (avg: ${Math.round(avgItems)}, expected: ${Math.round(avgItems - threshold * stddevItems)}-${Math.round(avgItems + threshold * stddevItems)})`,
          severity: m.agenda_item_count === 0 ? 'alert' : 'warning',
        })
      }
    }

    // Zero items is always an alert
    if (m.agenda_item_count === 0) {
      const alreadyFlagged = anomalies.some(
        (a) => a.meeting_id === m.meeting_id && a.anomaly_type.includes('item_count'),
      )
      if (!alreadyFlagged) {
        anomalies.push({
          meeting_id: m.meeting_id,
          meeting_date: m.meeting_date,
          anomaly_type: 'no_items',
          description: 'Meeting has no agenda items',
          severity: 'alert',
        })
      }
    }

    // No attendance
    if (m.attendance_count === 0) {
      anomalies.push({
        meeting_id: m.meeting_id,
        meeting_date: m.meeting_date,
        anomaly_type: 'no_attendance',
        description: 'No attendance records',
        severity: 'warning',
      })
    }
  }

  return anomalies
}
