'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState } from 'react'
import * as Collapsible from '@radix-ui/react-collapsible'
import { useOperatorMode } from './OperatorModeProvider'

export interface NextElectionLink { slug: string; label: string; description?: string }

const moreItems = [
  { href: '/elections/find-my-district', label: 'Find my district' },
  { href: '/topics', label: 'Browse topics' },
  { href: '/meetings/most-discussed', label: 'Most discussed' },
  { href: '/council/analytics', label: 'How the council votes' },
  { href: '/about', label: 'About Richmond Commons' },
]
const operatorItems = [
  { href: '/operator/decisions', label: 'Review decisions', operatorOnly: true },
  { href: '/operator/sync-health', label: 'Sync health', operatorOnly: true },
  { href: '/operator/recaps', label: 'Recaps', operatorOnly: true },
  { href: '/operator/settings', label: 'Settings', operatorOnly: true },
  { href: '/data-quality', label: 'Data quality', operatorOnly: true },
  { href: '/influence', label: 'Influence map', operatorOnly: true },
]
const navLink = 'flex min-h-11 items-center rounded-md px-3 text-sm font-medium text-slate-100 hover:bg-civic-navy-light hover:text-white'

function SearchForm({ mobile = false, onNavigate }: { mobile?: boolean; onNavigate?: () => void }) {
  const id = mobile ? 'mobile-nav-search' : 'desktop-nav-search'
  return <form action="/search" role="search" className="flex min-w-0 gap-2" onSubmit={onNavigate}>
    <label htmlFor={id} className="sr-only">Search meeting records by name or topic</label>
    <input id={id} type="search" name="q" placeholder="Name or topic" required className={`min-h-11 min-w-0 rounded-md border border-slate-400 bg-white px-3 text-base text-slate-900 placeholder:text-slate-600 ${mobile ? 'flex-1' : 'w-48'}`} />
    <button type="submit" className="min-h-11 rounded-md border border-slate-400 px-3 text-sm font-medium text-white hover:bg-civic-navy-light">Search</button>
  </form>
}

export default function Nav({ nextElection = null }: { nextElection?: NextElectionLink | null }) {
  const { isOperator } = useOperatorMode()
  const pathname = usePathname()
  const [mobileOpen, setMobileOpen] = useState(false)
  const primary = [
    { href: '/stories', label: 'Stories' },
    { href: '/meetings', label: 'Meetings' },
    { href: '/council', label: 'Council' },
    { href: nextElection ? `/elections/${nextElection.slug}` : '/elections', label: 'Elections' },
  ]
  const isCurrent = (href: string) => pathname === href || pathname.startsWith(`${href}/`)
  const close = () => setMobileOpen(false)
  return <header className="bg-civic-navy text-white">
    <a href="#main-content" className="sr-only z-50 rounded-md bg-white p-3 text-civic-navy focus:not-sr-only focus:absolute focus:left-3 focus:top-3">Skip to main content</a>
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
      <div className="hidden min-h-20 items-center justify-between gap-4 xl:flex">
        <Link href="/" className="flex min-h-11 shrink-0 items-center rounded-sm text-lg font-semibold tracking-tight">Richmond Commons</Link>
        <nav aria-label="Main navigation" className="flex items-center gap-1">
          {primary.map(item => <Link key={item.href} href={item.href} aria-current={isCurrent(item.href) ? 'page' : undefined} className={`${navLink} ${isCurrent(item.href) ? 'bg-civic-navy-light' : ''}`}>{item.label}</Link>)}
          <details className="relative" onKeyDown={event => { if (event.key === 'Escape') { event.currentTarget.open = false; event.currentTarget.querySelector('summary')?.focus() } }}>
            <summary className={`${navLink} cursor-pointer list-none gap-2`}>More <span aria-hidden="true">⌄</span></summary>
            <div className="absolute right-0 z-30 mt-2 w-64 rounded-md border border-slate-200 bg-white p-2 shadow-lg">{[...moreItems, ...(isOperator ? operatorItems : [])].map(item => <Link key={item.href} href={item.href} className="flex min-h-11 items-center rounded px-3 py-2 text-sm leading-6 text-slate-800 hover:bg-slate-100" onClick={event => { const details = event.currentTarget.closest('details'); if (details) details.open = false }}>{item.label}</Link>)}</div>
          </details>
        </nav>
        <SearchForm />
      </div>
      <Collapsible.Root open={mobileOpen} onOpenChange={setMobileOpen} className="xl:hidden">
        <div className="flex min-h-18 items-center justify-between gap-3"><Link href="/" onClick={close} className="flex min-h-11 items-center rounded-sm text-lg font-semibold tracking-tight">Richmond Commons</Link><Collapsible.Trigger className="min-h-11 rounded-md border border-slate-400 px-4 text-sm font-medium hover:bg-civic-navy-light">{mobileOpen ? 'Close' : 'Menu'}</Collapsible.Trigger></div>
        <Collapsible.Content className="pb-5" onKeyDown={event => { if (event.key === 'Escape') { close(); event.currentTarget.parentElement?.querySelector<HTMLButtonElement>('button[data-state]')?.focus() } }}>
          <nav aria-label="Mobile navigation" className="mb-5 grid gap-1 sm:grid-cols-2">{[...primary, ...moreItems, ...(isOperator ? operatorItems : [])].map(item => <Link key={item.href} href={item.href} onClick={close} aria-current={isCurrent(item.href) ? 'page' : undefined} className={`${navLink} ${isCurrent(item.href) ? 'bg-civic-navy-light' : ''}`}>{item.label}</Link>)}</nav>
          <SearchForm mobile onNavigate={close} />
        </Collapsible.Content>
      </Collapsible.Root>
    </div>
  </header>
}
