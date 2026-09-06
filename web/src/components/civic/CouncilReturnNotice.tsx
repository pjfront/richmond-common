'use client'

import { useSyncExternalStore } from 'react'
import { COUNCIL_RETURN_NOTICE } from '@/data/council-notices'
import { Localized } from './CivicLanguage'
import { civicLink } from './CivicStory'

const expiresAt = Date.parse(COUNCIL_RETURN_NOTICE.expiresAt)
const isBeforeMeetingDay = () => Date.now() < expiresAt
const wasCurrentOnServer = () => true
function subscribeToExpiry(onChange: () => void) {
  const timer = setTimeout(onChange, Math.max(0, expiresAt - Date.now()))
  return () => clearTimeout(timer)
}

/** Also hide an expired notice served from ISR or left open in a browser. */
export function CouncilReturnNotice() {
  const visible = useSyncExternalStore(subscribeToExpiry, isBeforeMeetingDay, wasCurrentOnServer)
  if (!visible) return null
  return <>
    <h3 className="text-xl font-semibold"><Localized {...COUNCIL_RETURN_NOTICE.heading} /></h3>
    <p className="mt-2 leading-7 text-slate-700"><Localized {...COUNCIL_RETURN_NOTICE.text} /></p>
    <p className="mt-3"><a href={COUNCIL_RETURN_NOTICE.sourceUrl} className={civicLink}><Localized {...COUNCIL_RETURN_NOTICE.sourceLabel} /><span aria-hidden="true">↗</span></a></p>
  </>
}
