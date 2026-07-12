import { NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'

export async function GET() {
  const { data, error } = await supabase
    .from('meetings')
    .select('id, meeting_date, meeting_type, transcript_recap, meeting_recap, meeting_summary, minutes_url')
    .eq('city_fips', '0660620')
    .order('meeting_date', { ascending: false })
    .limit(50)

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }

  const meetings = (data ?? []).map((m) => ({
    id: m.id,
    date: m.meeting_date,
    type: m.meeting_type ?? 'regular',
    hasTranscriptRecap: !!m.transcript_recap,
    hasMeetingRecap: !!m.meeting_recap,
    hasSummary: !!m.meeting_summary,
    hasMinutes: !!m.minutes_url,
    // How many days since the meeting (negative = in the future)
    daysAgo: Math.floor(
      (Date.now() - new Date(m.meeting_date + 'T00:00:00').getTime()) /
        (1000 * 60 * 60 * 24)
    ),
  }))

  return NextResponse.json({ meetings })
}
