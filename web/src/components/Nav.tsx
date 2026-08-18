'use client'

import * as Collapsible from '@radix-ui/react-collapsible'
import Link from 'next/link'
import { useState } from 'react'
import { useOperatorMode } from './OperatorModeProvider'

/** Public link to the next upcoming Richmond, California election. */
export interface NextElectionLink {
  slug: string
  label: string
  description?: string
}

interface PrimaryLink {
  href: string
  label: string
}

function primaryLinks(nextElection: NextElectionLink | null): PrimaryLink[] {
  return [
    { href: '/meetings', label: 'Meetings' },
    nextElection
      ? { href: `/elections/${nextElection.slug}`, label: nextElection.label }
      : { href: '/elections/find-my-district', label: 'Elections' },
    { href: '/council', label: 'Council' },
    { href: '/subscribe?source=nav', label: 'Stay informed' },
  ]
}

function SearchForm({ id, onSubmit }: { id: string; onSubmit?: () => void }) {
  return (
    <form action="/search" method="get" role="search" className="flex gap-2" onSubmit={onSubmit}>
      <label htmlFor={id} className="sr-only">Search Richmond Commons</label>
      <input
        id={id}
        name="q"
        type="search"
        required
        placeholder="Search"
        className="min-h-11 min-w-0 flex-1 rounded-md border border-white/30 bg-white/10 px-3 text-base text-white placeholder:text-slate-300 focus:border-white focus:outline-none focus:ring-2 focus:ring-white/60 lg:w-40"
      />
      <button
        type="submit"
        className="min-h-11 rounded-md border border-white/30 px-3 text-sm font-semibold text-white hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-civic-navy"
      >
        Search
      </button>
    </form>
  )
}

export default function Nav({ nextElection = null }: { nextElection?: NextElectionLink | null } = {}) {
  const { isOperator } = useOperatorMode()
  const [open, setOpen] = useState(false)
  const links = primaryLinks(nextElection)

  return (
    <nav className="bg-civic-navy text-white" aria-label="Main navigation">
      <Collapsible.Root open={open} onOpenChange={setOpen} asChild>
        <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
          <div className="flex min-h-16 items-center justify-between gap-4">
            <div className="flex shrink-0 items-center gap-2">
              <Link
                href="/"
                className="inline-flex min-h-11 items-center text-lg font-bold tracking-tight transition-colors hover:text-civic-amber-light focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-civic-navy"
              >
                Richmond Commons
              </Link>
              {isOperator && (
                <span className="rounded bg-civic-amber/20 px-1.5 py-0.5 font-mono text-[10px] text-civic-amber-light">
                  OP
                </span>
              )}
            </div>

            <div className="hidden items-center gap-1 lg:flex">
              {links.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className="inline-flex min-h-11 items-center rounded px-3 py-2 text-sm font-medium text-slate-100 transition-colors hover:bg-civic-navy-light hover:text-white focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-civic-navy"
                >
                  {link.label}
                </Link>
              ))}
              {isOperator && (
                <Link
                  href="/operator/decisions"
                  className="inline-flex min-h-11 items-center rounded px-3 py-2 text-sm font-medium text-civic-amber-light transition-colors hover:bg-civic-navy-light hover:text-white focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-civic-navy"
                >
                  Operator
                </Link>
              )}
              <div className="ml-2 border-l border-white/20 pl-3">
                <SearchForm id="nav-search-desktop" />
              </div>
            </div>

            <div className="lg:hidden">
              <Collapsible.Trigger asChild>
                <button
                  type="button"
                  className="inline-flex size-11 items-center justify-center rounded-md text-white hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-civic-navy"
                  aria-label={open ? 'Close navigation menu' : 'Open navigation menu'}
                >
                  {open ? (
                    <svg aria-hidden="true" viewBox="0 0 24 24" className="size-6" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M6 6l12 12M18 6 6 18" />
                    </svg>
                  ) : (
                    <svg aria-hidden="true" viewBox="0 0 24 24" className="size-6" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M4 7h16M4 12h16M4 17h16" />
                    </svg>
                  )}
                </button>
              </Collapsible.Trigger>
            </div>
          </div>

          <Collapsible.Content className="border-t border-white/15 py-3 lg:hidden">
            <div className="grid gap-1">
              {links.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  onClick={() => setOpen(false)}
                  className="inline-flex min-h-11 items-center rounded px-3 py-2 text-base font-medium text-slate-100 hover:bg-civic-navy-light hover:text-white focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-civic-navy"
                >
                  {link.label}
                </Link>
              ))}
              {isOperator && (
                <Link
                  href="/operator/decisions"
                  onClick={() => setOpen(false)}
                  className="inline-flex min-h-11 items-center rounded px-3 py-2 text-base font-medium text-civic-amber-light hover:bg-civic-navy-light hover:text-white focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-civic-navy"
                >
                  Operator
                </Link>
              )}
              <div className="mt-2 border-t border-white/15 pt-3">
                <SearchForm id="nav-search-mobile" onSubmit={() => setOpen(false)} />
              </div>
            </div>
          </Collapsible.Content>
        </div>
      </Collapsible.Root>
    </nav>
  )
}
