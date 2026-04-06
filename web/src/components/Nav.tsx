'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState, useRef, useEffect, useCallback } from 'react'
import { useOperatorMode } from './OperatorModeProvider'

interface NavItem {
  href: string
  label: string
  operatorOnly?: boolean
  description?: string
}

interface NavGroup {
  label: string
  items: NavItem[]
}

const navGroups: NavGroup[] = [
  {
    label: 'Meetings',
    items: [
      { href: '/meetings', label: 'All Meetings', description: 'Browse council meeting agendas and votes' },
      { href: '/council/stats', label: 'Topics & Trends', description: 'Vote categories, controversy scores', operatorOnly: true },
    ],
  },
  {
    label: 'Council',
    items: [
      { href: '/council', label: 'Council Members', description: 'Profiles, voting records, donors' },
      { href: '/council/coalitions', label: 'Voting Coalitions', description: 'Who votes together and how often', operatorOnly: true },
      { href: '/commissions', label: 'Boards & Commissions', description: 'Rosters, vacancies, terms', operatorOnly: true },
    ],
  },
  {
    label: 'Elections',
    items: [
      { href: '/elections/find-my-district', label: 'Find My District', description: 'Look up your council district and representatives' },
      { href: '/elections', label: 'All Elections', description: 'Candidates, fundraising, and voter info' },
      { href: '/influence', label: 'Influence Map', description: 'Campaign finance connections by official', operatorOnly: true },
      { href: '/council/patterns', label: 'Donor Patterns', description: 'Shared donors, category concentration', operatorOnly: true },
      { href: '/reports', label: 'Financial Reports', description: 'Per-meeting contribution analysis', operatorOnly: true },
    ],
  },
  {
    label: 'Records',
    items: [
      { href: '/public-records', label: 'Public Records', description: 'CPRA request compliance tracking', operatorOnly: true },
      { href: '/data-quality', label: 'Data Quality', description: 'Freshness and completeness monitoring', operatorOnly: true },
    ],
  },
  {
    label: 'Operator',
    items: [
      { href: '/operator/decisions', label: 'Decisions', description: 'Pending operator decisions', operatorOnly: true },
      { href: '/operator/sync-health', label: 'Sync Health', description: 'Data source freshness monitoring', operatorOnly: true },
      { href: '/operator/settings', label: 'Settings', description: 'AI scoring parameters', operatorOnly: true },
    ],
  },
]

function NavDropdown({ group, isOperator }: { group: NavGroup; isOperator: boolean }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const visibleItems = group.items.filter(item => !item.operatorOnly || isOperator)
  if (visibleItems.length === 0) return null

  // If every item is operator-only, use amber styling for the trigger
  const isOperatorGroup = group.items.every(item => item.operatorOnly)

  // Single item — render as direct link, no dropdown
  if (visibleItems.length === 1) {
    return (
      <Link
        href={visibleItems[0].href}
        className="px-3 py-2 rounded text-sm font-medium text-slate-200 hover:text-white hover:bg-civic-navy-light transition-colors"
      >
        {group.label}
      </Link>
    )
  }

  const handleMouseEnter = () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
    setOpen(true)
  }

  const handleMouseLeave = () => {
    timeoutRef.current = setTimeout(() => setOpen(false), 150)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      setOpen(prev => !prev)
    }
    if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div
      ref={ref}
      className="relative"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <button
        type="button"
        className={`px-3 py-2 rounded text-sm font-medium hover:text-white hover:bg-civic-navy-light transition-colors flex items-center gap-1 ${isOperatorGroup ? 'text-civic-amber-light' : 'text-slate-200'}`}
        aria-expanded={open}
        aria-haspopup="true"
        onKeyDown={handleKeyDown}
        onClick={() => setOpen(prev => !prev)}
      >
        {group.label}
        <svg className={`w-3 h-3 transition-transform ${open ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div
          className="absolute top-full left-0 mt-1 w-64 bg-white rounded-lg shadow-lg border border-slate-200 py-1 z-50"
          role="menu"
        >
          {visibleItems.map(item => (
            <Link
              key={item.href}
              href={item.href}
              role="menuitem"
              className="block px-4 py-2.5 hover:bg-slate-50 transition-colors group"
              onClick={() => setOpen(false)}
            >
              <span className="text-sm font-medium text-slate-900 group-hover:text-civic-navy flex items-center gap-2">
                {item.label}
                {item.operatorOnly && (
                  <span className="text-[9px] font-mono bg-civic-amber/10 text-civic-amber px-1 py-0.5 rounded">OP</span>
                )}
              </span>
              {item.description && (
                <span className="text-xs text-slate-500 mt-0.5 block">{item.description}</span>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}

function NavSearch() {
  const router = useRouter()
  const [query, setQuery] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = query.trim()
    if (trimmed) {
      router.push(`/search?q=${encodeURIComponent(trimmed)}`)
      setQuery('')
      inputRef.current?.blur()
    }
  }

  // Keyboard shortcut: / to focus search
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes((e.target as HTMLElement)?.tagName)) {
        e.preventDefault()
        inputRef.current?.focus()
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [])

  return (
    <form onSubmit={handleSubmit} className="hidden sm:block" role="search">
      <div className="relative">
        <input
          ref={inputRef}
          type="search"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search…"
          aria-label="Search the site"
          className="w-36 lg:w-44 px-3 py-1.5 pl-8 text-sm bg-civic-navy-light/50 border border-slate-500/30 rounded-md text-white placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-civic-amber-light focus:border-civic-amber-light focus:w-56 transition-all"
        />
        <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
      </div>
    </form>
  )
}

function MobileMenu({ isOperator }: { isOperator: boolean }) {
  const [open, setOpen] = useState(false)
  const router = useRouter()
  const [mobileQuery, setMobileQuery] = useState('')

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = mobileQuery.trim()
    if (trimmed) {
      router.push(`/search?q=${encodeURIComponent(trimmed)}`)
      setMobileQuery('')
      setOpen(false)
    }
  }

  // Close on Escape
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') setOpen(false)
  }, [])

  useEffect(() => {
    if (open) {
      document.addEventListener('keydown', handleKeyDown)
      return () => document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open, handleKeyDown])

  return (
    <div className="sm:hidden">
      <button
        type="button"
        onClick={() => setOpen(prev => !prev)}
        className="p-2 rounded text-slate-200 hover:text-white hover:bg-civic-navy-light transition-colors"
        aria-expanded={open}
        aria-label={open ? 'Close menu' : 'Open menu'}
      >
        {open ? (
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        ) : (
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        )}
      </button>

      {open && (
        <div className="absolute top-16 left-0 right-0 bg-civic-navy border-t border-civic-navy-light z-50 shadow-lg">
          {/* Mobile search */}
          <form onSubmit={handleSearch} className="px-4 py-3 border-b border-civic-navy-light" role="search">
            <input
              type="search"
              value={mobileQuery}
              onChange={e => setMobileQuery(e.target.value)}
              placeholder="Search a name, topic, or address…"
              aria-label="Search the site"
              className="w-full px-3 py-2 text-sm bg-civic-navy-light/50 border border-slate-500/30 rounded-md text-white placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-civic-amber-light"
            />
          </form>

          {/* Mobile nav groups */}
          <div className="px-2 py-2 max-h-[70vh] overflow-y-auto">
            {navGroups.map(group => {
              const visibleItems = group.items.filter(item => !item.operatorOnly || isOperator)
              if (visibleItems.length === 0) return null
              return (
                <div key={group.label} className="mb-2">
                  <div className="px-3 py-1.5 text-xs font-semibold text-slate-400 uppercase tracking-wider">
                    {group.label}
                  </div>
                  {visibleItems.map(item => (
                    <Link
                      key={item.href}
                      href={item.href}
                      className="block px-4 py-2.5 rounded text-sm text-slate-200 hover:text-white hover:bg-civic-navy-light transition-colors"
                      onClick={() => setOpen(false)}
                    >
                      <span className="flex items-center gap-2">
                        {item.label}
                        {item.operatorOnly && (
                          <span className="text-[9px] font-mono bg-civic-amber/20 text-civic-amber-light px-1 py-0.5 rounded">OP</span>
                        )}
                      </span>
                    </Link>
                  ))}
                </div>
              )
            })}

            {/* About + operator items */}
            <div className="mb-2">
              <div className="px-3 py-1.5 text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Info
              </div>
              <Link
                href="/about"
                className="block px-4 py-2.5 rounded text-sm text-slate-200 hover:text-white hover:bg-civic-navy-light transition-colors"
                onClick={() => setOpen(false)}
              >
                About
              </Link>
              {isOperator && (
                <>
                  <Link
                    href="/operator/decisions"
                    className="block px-4 py-2.5 rounded text-sm text-civic-amber-light hover:text-white hover:bg-civic-navy-light transition-colors"
                    onClick={() => setOpen(false)}
                  >
                    <span className="flex items-center gap-2">
                      Decisions
                      <span className="text-[9px] font-mono bg-civic-amber/20 text-civic-amber-light px-1 py-0.5 rounded">OP</span>
                    </span>
                  </Link>
                  <Link
                    href="/operator/sync-health"
                    className="block px-4 py-2.5 rounded text-sm text-civic-amber-light hover:text-white hover:bg-civic-navy-light transition-colors"
                    onClick={() => setOpen(false)}
                  >
                    <span className="flex items-center gap-2">
                      Sync Health
                      <span className="text-[9px] font-mono bg-civic-amber/20 text-civic-amber-light px-1 py-0.5 rounded">OP</span>
                    </span>
                  </Link>
                  <Link
                    href="/operator/settings"
                    className="block px-4 py-2.5 rounded text-sm text-civic-amber-light hover:text-white hover:bg-civic-navy-light transition-colors"
                    onClick={() => setOpen(false)}
                  >
                    <span className="flex items-center gap-2">
                      Settings
                      <span className="text-[9px] font-mono bg-civic-amber/20 text-civic-amber-light px-1 py-0.5 rounded">OP</span>
                    </span>
                  </Link>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function Nav() {
  const { isOperator } = useOperatorMode()

  return (
    <nav className="bg-civic-navy text-white" aria-label="Main navigation">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <div className="flex items-center gap-2 shrink-0">
            <Link href="/" className="text-lg font-bold tracking-tight hover:text-civic-amber-light transition-colors">
              Richmond Commons
            </Link>
            {isOperator && (
              <span className="text-[10px] font-mono bg-civic-amber/20 text-civic-amber-light px-1.5 py-0.5 rounded">
                OP
              </span>
            )}
          </div>

          {/* Desktop nav */}
          <div className="hidden sm:flex items-center gap-0.5">
            {navGroups.map(group => (
              <NavDropdown key={group.label} group={group} isOperator={isOperator} />
            ))}

            <Link
              href="/about"
              className="px-3 py-2 rounded text-sm font-medium text-slate-200 hover:text-white hover:bg-civic-navy-light transition-colors"
            >
              About
            </Link>

            <div className="ml-2 border-l border-slate-500/30 pl-2">
              <NavSearch />
            </div>
          </div>

          {/* Mobile menu toggle */}
          <MobileMenu isOperator={isOperator} />
        </div>
      </div>
    </nav>
  )
}
