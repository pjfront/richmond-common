import { richmondDateKey } from '@/lib/richmond-date'
import type { ResidentSnapshot } from '@/lib/queries/civic-stories'

/** Dated official notice, independent of the not-yet-published agenda. */
export const COUNCIL_RETURN_NOTICE = {
  meetingDate: '2026-09-15',
  expiresAt: '2026-09-15T00:00:00-07:00',
  sourceDate: '2026-09-04',
  sourceUrl: 'https://www.ci.richmond.ca.us/Archive.aspx?ADID=17876#page=3',
  checkedAt: '2026-09-06',
  heading: { en: 'Council resumes September 15', es: 'El Concejo vuelve el 15 de septiembre' },
  text: {
    en: 'The City Manager’s September 4 report says regular council meetings resume September 15 after recess. An agenda is not yet available in the records here. Check the city’s calendar for the agenda and participation details.',
    es: 'El informe del administrador municipal del 4 de septiembre indica que las reuniones regulares del Concejo se reanudan el 15 de septiembre después del receso. Todavía no hay una agenda en los registros disponibles aquí. Consulte el calendario municipal para ver la agenda y los detalles para participar.',
  },
  sourceLabel: { en: 'City Manager’s September 4 report · page 3', es: 'Informe del administrador municipal del 4 de septiembre · página 3' },
} as const

/** Expire at the start of the meeting day: the source supplies no start time. */
export function getCouncilReturnNotice(
  snapshot: Pick<ResidentSnapshot, 'status' | 'upcoming'>,
  now = new Date(),
) {
  const today = richmondDateKey(now)
  return snapshot.status === 'available' && snapshot.upcoming.length === 0 &&
    today >= COUNCIL_RETURN_NOTICE.checkedAt && today < COUNCIL_RETURN_NOTICE.meetingDate
    ? COUNCIL_RETURN_NOTICE : null
}
