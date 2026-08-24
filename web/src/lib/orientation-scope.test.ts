import { describe, expect, it } from 'vitest'
import {
  COUNCIL_ORIENTATION_SOURCE_COLUMNS,
  isRichmondCouncilOrientationMeeting,
} from './orientation-scope'

describe('regular City Council orientation scope', () => {
  it('requires both a regular meeting and the canonical council body type', () => {
    expect(isRichmondCouncilOrientationMeeting({
      meeting_type: 'regular',
      bodies: { body_type: 'city_council' },
    })).toBe(true)
    expect(isRichmondCouncilOrientationMeeting({
      meeting_type: 'regular',
      bodies: { body_type: 'commission' },
    })).toBe(false)
    expect(isRichmondCouncilOrientationMeeting({
      meeting_type: 'special',
      bodies: { body_type: 'city_council' },
    })).toBe(false)
    expect(isRichmondCouncilOrientationMeeting({
      meeting_type: 'regular',
      bodies: null,
    })).toBe(false)
  })

  it('uses an inner body relation so an unlinked meeting cannot be selected', () => {
    expect(COUNCIL_ORIENTATION_SOURCE_COLUMNS).toContain('bodies!inner(body_type)')
  })
})
