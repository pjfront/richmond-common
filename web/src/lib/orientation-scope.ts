export const RICHMOND_COUNCIL_BODY_TYPE = 'city_council' as const

export const COUNCIL_ORIENTATION_SOURCE_COLUMNS =
  'id, meeting_date, orientation_preview, orientation_preview_provenance, agenda_url, bodies!inner(body_type)' as const

interface OrientationScopeMeeting {
  meeting_type: string
  bodies: { body_type: string } | null
}

/** Keep every automated preview on the public regular-council promise. */
export function isRichmondCouncilOrientationMeeting(
  meeting: OrientationScopeMeeting,
): boolean {
  return meeting.meeting_type === 'regular'
    && meeting.bodies?.body_type === RICHMOND_COUNCIL_BODY_TYPE
}
