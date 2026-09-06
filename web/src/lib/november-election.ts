/** Source-checked municipal election facts. Dates are calendar dates in California. */
export const NOVEMBER_ELECTION = {
  date: '2026-11-03',
  checkedAt: '2026-09-06',
  certification: 'https://www.richmondca.gov/Archive.aspx?ADID=17785',
  bondResolution: 'https://www.richmondca.gov/Archive.aspx?ADID=17838',
  votingDates: 'https://www.sos.ca.gov/elections/upcoming-elections/general-election-november-3-2026/key-dates-deadlines',
  filingSchedule: 'https://www.fppc.ca.gov/siteassets/documents/tad/filing_schedules/2026/2026_local_nov_01_cand_final.pdf',
  independentSchedule: 'https://www.fppc.ca.gov/siteassets/documents/tad/filing_schedules/2026/2026_local_nov_05_md_ie_final.pdf',
  county: 'https://www.contracostavote.gov/',
} as const

export const NOVEMBER_CANDIDATES = [
  { name: 'Ahmad Anderson', committeeId: '1481105', slug: 'ahmad-anderson' },
  { name: 'Claudia Jimenez', committeeId: '1488504', slug: 'claudia-jimenez' },
] as const

export const NOVEMBER_DATES = [
  { date: '2026-09-24', title: 'First pre-election campaign reports due', detail: 'Covers July 1–September 19.', kind: 'filing' },
  { date: '2026-10-05', title: 'Early voting begins', detail: 'County ballot mailing begins no later than this date.', kind: 'voting' },
  { date: '2026-10-19', title: 'Regular voter registration deadline', detail: 'Conditional registration remains available October 20–November 3.', kind: 'voting' },
  { date: '2026-10-22', title: 'Second pre-election campaign reports due', detail: 'Covers September 20–October 17.', kind: 'filing' },
  { date: '2026-11-03', title: 'Election day', detail: 'Polls open 7 a.m.–8 p.m. Conditional registration is still available.', kind: 'voting' },
] as const

export function formatCivicDate(value: string): string {
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' })
    .format(new Date(value.length === 10 ? `${value}T12:00:00Z` : value))
}

export function electionCalendar(): string {
  const escape = (text: string) => text.replaceAll('\\', '\\\\').replaceAll(';', '\\;').replaceAll(',', '\\,').replaceAll('\n', '\\n')
  const lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Richmond Commons//Election Dates//EN', 'CALSCALE:GREGORIAN']
  for (const item of NOVEMBER_DATES) {
    const next = new Date(`${item.date}T12:00:00Z`)
    next.setUTCDate(next.getUTCDate() + 1)
    lines.push('BEGIN:VEVENT', `UID:2026-${item.date}@richmondcommons.org`, 'DTSTAMP:20260906T120000Z',
      `DTSTART;VALUE=DATE:${item.date.replaceAll('-', '')}`,
      `DTEND;VALUE=DATE:${next.toISOString().slice(0, 10).replaceAll('-', '')}`,
      `SUMMARY:${escape(`Richmond: ${item.title}`)}`, `DESCRIPTION:${escape(item.detail)}`,
      `URL:${item.kind === 'filing' ? NOVEMBER_ELECTION.filingSchedule : NOVEMBER_ELECTION.votingDates}`, 'END:VEVENT')
  }
  lines.push('END:VCALENDAR')
  // Fold at 75 UTF-8 octets without splitting multibyte characters (RFC 5545).
  const fold = (line: string) => {
    let result = ''; let bytes = 0
    for (const char of line) {
      const size = Buffer.byteLength(char, 'utf8')
      if (bytes + size > 75) { result += '\r\n '; bytes = 1 }
      result += char; bytes += size
    }
    return result
  }
  return lines.map(fold).join('\r\n') + '\r\n'
}
