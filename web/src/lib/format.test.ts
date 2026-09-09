import { describe, expect, it } from 'vitest'
import { agendaItemPath } from './format'

describe('source meeting fallback for unaddressable agenda records', () => {
  it.each([null, undefined, '', '  ', '<unknown>', ' <UNKNOWN> ', 'unknown', 'N/A', '-', '—'])(
    'opens the source meeting for missing or placeholder item number %s', itemNumber => {
      expect(agendaItemPath('meeting-1', itemNumber)).toBe('/meetings/meeting-1')
    },
  )

  it.each([
    ['W.3.b', 'w.3.b'], ['H-1', 'h-1'], ['10', '10'], ['Public Hearing', 'public%20hearing'],
    ['A/B', 'a%2Fb'], ['Unknown Project', 'unknown%20project'],
  ])('preserves canonical addressing for a real source identifier %s', (itemNumber, encoded) => {
    expect(agendaItemPath('meeting-1', itemNumber)).toBe(`/meetings/meeting-1/items/${encoded}`)
  })
})
