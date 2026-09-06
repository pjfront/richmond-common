import { electionCalendar } from '@/lib/november-election'

export function GET() {
  return new Response(electionCalendar(), { headers: {
    'Content-Type': 'text/calendar; charset=utf-8',
    'Content-Disposition': 'attachment; filename="richmond-november-2026.ics"',
    'Cache-Control': 'public, max-age=3600',
  } })
}
