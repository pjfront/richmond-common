'use client'

import Link from 'next/link'
import { useOperatorMode } from './OperatorModeProvider'

const navLinks = [
  { href: '/meetings', label: 'Meetings' },
  { href: '/council', label: 'Council' },
  { href: '/council/stats', label: 'Stats' },
  { href: '/council/coalitions', label: 'Coalitions' },
  { href: '/council/patterns', label: 'Patterns' },
  { href: '/commissions', label: 'Boards' },
  { href: '/public-records', label: 'Public Records' },
  { href: '/reports', label: 'Reports' },
  { href: '/search', label: 'Search', operatorOnly: true },
  { href: '/financial-connections', label: 'Connections', operatorOnly: true },
  { href: '/data-quality', label: 'Data Quality' },
  { href: '/about', label: 'About' },
]

export default function Nav() {
  const { isOperator } = useOperatorMode()

  return (
    <nav className="bg-civic-navy text-white">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center gap-2">
            <Link href="/" className="text-lg font-bold tracking-tight hover:text-civic-amber-light">
              Richmond Transparency Project
            </Link>
            {isOperator && (
              <span className="text-[10px] font-mono bg-civic-amber/20 text-civic-amber-light px-1.5 py-0.5 rounded">
                OP
              </span>
            )}
          </div>
          <div className="flex gap-1">
            {navLinks
              .filter(({ operatorOnly }) => !operatorOnly || isOperator)
              .map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                className="px-3 py-2 rounded text-sm font-medium text-slate-200 hover:text-white hover:bg-civic-navy-light transition-colors"
              >
                {label}
              </Link>
            ))}
            {isOperator && (
              <Link
                href="/operator/decisions"
                className="px-3 py-2 rounded text-sm font-medium text-civic-amber-light hover:text-white hover:bg-civic-navy-light transition-colors"
              >
                Decisions
              </Link>
            )}
          </div>
        </div>
      </div>
    </nav>
  )
}
