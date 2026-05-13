'use client'

import Link from 'next/link'
import { useOperatorMode } from '@/components/OperatorModeProvider'

export type AnalyticsTab = 'voting' | 'stats' | 'patterns'

interface TabDef {
  id: AnalyticsTab
  label: string
  operatorOnly: boolean
}

const TABS: TabDef[] = [
  { id: 'voting', label: 'How the Council Votes', operatorOnly: false },
  { id: 'stats', label: 'Topics & Trends', operatorOnly: true },
  { id: 'patterns', label: 'Donor Patterns', operatorOnly: true },
]

/**
 * Tab navigation for `/council/analytics`.
 *
 * Tabs are real <Link>s, not JS button handlers. Each switch is a normal
 * server-rendered navigation, which keeps the page fully accessible without
 * JS and indexable per-tab. The client side exists only so operator-only
 * tabs can be hidden from public visitors based on the cookie cached in
 * <OperatorModeProvider>.
 *
 * ARIA: the rendered markup is a `role="tablist"` with `role="tab"` links
 * carrying `aria-selected`. Screen readers identify it as a tab group;
 * crawlers see normal navigation. Best of both.
 */
export default function AnalyticsTabs({ activeTab }: { activeTab: AnalyticsTab }) {
  const { isOperator } = useOperatorMode()
  const visibleTabs = TABS.filter((t) => !t.operatorOnly || isOperator)

  return (
    <div
      role="tablist"
      aria-label="Council analytics views"
      className="flex flex-wrap gap-1 border-b border-slate-200 mb-6"
    >
      {visibleTabs.map((tab) => {
        const isActive = tab.id === activeTab
        return (
          <Link
            key={tab.id}
            href={tab.id === 'voting' ? '/council/analytics' : `/council/analytics?tab=${tab.id}`}
            role="tab"
            aria-selected={isActive}
            scroll={false}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              isActive
                ? 'border-civic-navy text-civic-navy'
                : 'border-transparent text-slate-500 hover:text-civic-navy hover:border-slate-300'
            }`}
          >
            <span className="inline-flex items-center gap-2">
              {tab.label}
              {tab.operatorOnly && (
                <span className="text-[9px] font-mono bg-civic-amber/10 text-civic-amber px-1 py-0.5 rounded">
                  OP
                </span>
              )}
            </span>
          </Link>
        )
      })}
    </div>
  )
}
