import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const navigation = vi.hoisted(() => ({
  notFound: vi.fn(),
  permanentRedirect: vi.fn(),
}))

const queryMocks = vi.hoisted(() => ({
  getAgendaItemBasic: vi.fn(),
}))

vi.mock('next/navigation', () => navigation)

vi.mock('@/lib/queries', () => ({
  getAgendaItemBasic: queryMocks.getAgendaItemBasic,
}))

import LegacyInfluenceItemPage from '@/app/influence/item/[id]/page'
import InfluenceMethodologyPage, {
  metadata as influenceMethodologyMetadata,
} from '@/app/influence/methodology/page'

function source(relativePath: string): string {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), 'utf8')
}

describe('influence route containment', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    navigation.permanentRedirect.mockImplementation(() => {
      throw new Error('NEXT_PERMANENT_REDIRECT')
    })
  })

  it('keeps public methodology available but noindexed and free of gated dead ends', () => {
    const markup = renderToStaticMarkup(<InfluenceMethodologyPage />)

    expect(influenceMethodologyMetadata.robots).toEqual({
      index: false,
      follow: false,
    })
    expect(markup).toContain('href="/elections/methodology"')
    expect(markup).toContain('← How we show campaign contributions')
    expect(markup).not.toContain('href="/influence"')
  })

  it('keeps the influence IA hidden from residents', () => {
    const nav = source('../components/Nav.tsx')

    expect(nav).not.toContain("href: '/financial-connections'")
    expect(nav).toMatch(
      /href: '\/influence',[^\n]+operatorOnly: true/,
    )
  })

  it('preserves the legacy item redirect to its canonical meeting-item route', async () => {
    queryMocks.getAgendaItemBasic.mockResolvedValue({
      meeting_id: 'meeting-1',
      item_number: 'CC-1',
    })

    await expect(
      LegacyInfluenceItemPage({ params: Promise.resolve({ id: 'legacy-1' }) }),
    ).rejects.toThrow('NEXT_PERMANENT_REDIRECT')

    expect(queryMocks.getAgendaItemBasic).toHaveBeenCalledWith('legacy-1')
    expect(navigation.permanentRedirect).toHaveBeenCalledWith(
      '/meetings/meeting-1/items/cc-1',
    )
  })
})
