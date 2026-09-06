import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import FollowSubject from './FollowSubject'
import SubscribePage from '@/app/subscribe/page'
import PreferencesPanel from './PreferencesPanel'

describe('truthful subject follow journeys', () => {
  it('carries the approved subject into signup and clearly says delivery has not started', async () => {
    const cta = renderToStaticMarkup(<FollowSubject subject="2026-general" />)
    expect(cta).toContain('href="/subscribe?follow=2026-general"')
    expect(cta).toContain('weekly email')
    expect(cta).toContain('has not started')
    const page = renderToStaticMarkup(await SubscribePage({ searchParams: Promise.resolve({ follow: '2026-general' }) }))
    expect(page).toContain('November 2026 election and campaign money')
    expect(page).toContain('Save this follow')
    expect(page).toContain('does not change its saved choices')
    expect(page).toContain('General council previews and recaps are off')
    expect(page).not.toContain('you will receive updates immediately')
  })
  it('does not create an unknown follow or reflect it into a form', async () => {
    expect(renderToStaticMarkup(<FollowSubject subject="unlisted-subject" />)).toBe('')
    const page = renderToStaticMarkup(await SubscribePage({ searchParams: Promise.resolve({ follow: 'unlisted-subject' }) }))
    expect(page).not.toContain('unlisted-subject')
    expect(page).not.toContain('Save this follow')
  })
  it('keeps council consent visibly off for a subject-only subscriber and labels saved context truthfully', () => {
    const html = renderToStaticMarkup(<PreferencesPanel token="private" initialPreferences={{ topics: [], districts: [], candidates: [], subjects: ['2026-general'], receiveCouncilUpdates: false }} candidates={[]} councilMembers={[]} />)
    expect(html.match(/checked=""/g)).toHaveLength(1)
    expect(html).toContain('Include council previews and recaps')
    expect(html).toContain('They do not filter email delivery')
    expect(html).not.toContain('updates on everything')
    expect(html).toContain('has not started')
  })
})
