import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import CommissionCard from './CommissionCard'
import type { CommissionWithStats } from '@/lib/types'
it('does not equate expired terms with vacant seats', () => {
  const row = { id: 'one', name: 'Planning Commission', commission_type: 'advisory', member_count: 3, holdover_count: 2, num_seats: 7 } as CommissionWithStats
  const html = renderToStaticMarkup(<CommissionCard commission={row} />)
  expect(html).toContain('5 listed current members')
  expect(html).toContain('2 with expired recorded terms')
  expect(html).not.toMatch(/vacant|3\/7|holdover/)
})
