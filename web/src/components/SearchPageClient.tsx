'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { useSearchParams } from 'next/navigation'
import type { SearchResult, SearchResultType, SearchResponse } from '@/lib/types'
import SearchResultCard from './SearchResultCard'

const TYPE_FILTERS: Array<{ value: SearchResultType | 'all'; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'agenda_item', label: 'Agenda Items' },
  { value: 'official', label: 'Officials' },
  { value: 'commission', label: 'Commissions' },
  { value: 'vote_explainer', label: 'Votes' },
]

const DEBOUNCE_MS = 300
const PAGE_SIZE = 20

export default function SearchPageClient() {
  const searchParams = useSearchParams()
  const initialQuery = searchParams.get('q') ?? ''

  const [query, setQuery] = useState(initialQuery)
  const [typeFilter, setTypeFilter] = useState<SearchResultType | 'all'>('all')
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [totalLoaded, setTotalLoaded] = useState(0)
  const [searched, setSearched] = useState(false)

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const doSearch = useCallback(async (q: string, type: SearchResultType | 'all', offset: number, append: boolean) => {
    if (q.length < 2) {
      if (!append) {
        setResults([])
        setSearched(false)
      }
      return
    }

    // Cancel previous in-flight request
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setLoading(true)

    const params = new URLSearchParams({ q, limit: String(PAGE_SIZE), offset: String(offset) })
    if (type !== 'all') params.set('type', type)

    try {
      const res = await fetch(`/api/search?${params}`, { signal: controller.signal })
      if (!res.ok) {
        setLoading(false)
        return
      }
      const data: SearchResponse = await res.json()

      setResults((prev) => append ? [...prev, ...data.results] : data.results)
      setTotalLoaded((prev) => append ? prev + data.results.length : data.results.length)
      setHasMore(data.results.length === PAGE_SIZE)
      setSearched(true)
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        console.error('Search error:', err)
      }
    } finally {
      setLoading(false)
    }
  }, [])

  // Debounced search on query/type change
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      doSearch(query, typeFilter, 0, false)
      // Sync URL for shareable links
      const url = query.length >= 2
        ? `${window.location.pathname}?q=${encodeURIComponent(query)}${typeFilter !== 'all' ? `&type=${typeFilter}` : ''}`
        : window.location.pathname
      window.history.replaceState(null, '', url)
    }, DEBOUNCE_MS)

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [query, typeFilter, doSearch])

  const loadMore = () => {
    doSearch(query, typeFilter, totalLoaded, true)
  }

  return (
    <div>
      {/* Search input */}
      <div className="mb-4">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search agenda items, officials, commissions, votes..."
          className="w-full px-4 py-3 rounded-lg border border-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-civic-navy/30 focus:border-civic-navy"
          autoFocus
        />
      </div>

      {/* Type filter pills */}
      <div className="flex flex-wrap gap-2 mb-6">
        {TYPE_FILTERS.map(({ value, label }) => (
          <button
            key={value}
            onClick={() => setTypeFilter(value)}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              typeFilter === value
                ? 'bg-civic-navy text-white'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Results */}
      {loading && results.length === 0 && (
        <p className="text-sm text-slate-500 py-8 text-center">Searching...</p>
      )}

      {searched && !loading && results.length === 0 && (
        <div className="text-center py-12">
          <p className="text-slate-600 text-sm">No results found for &ldquo;{query}&rdquo;</p>
          <p className="text-slate-400 text-xs mt-1">Try different keywords or remove the type filter.</p>
        </div>
      )}

      {results.length > 0 && (
        <>
          <p className="text-xs text-slate-400 mb-3">
            {totalLoaded} result{totalLoaded !== 1 ? 's' : ''} for &ldquo;{query}&rdquo;
            {typeFilter !== 'all' && ` in ${TYPE_FILTERS.find((f) => f.value === typeFilter)?.label}`}
          </p>
          <div className="space-y-3">
            {results.map((r) => (
              <SearchResultCard key={`${r.result_type}-${r.id}`} result={r} />
            ))}
          </div>
          {hasMore && (
            <button
              onClick={loadMore}
              disabled={loading}
              className="mt-4 w-full py-2 text-sm font-medium text-civic-navy hover:text-civic-navy-light border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors disabled:opacity-50"
            >
              {loading ? 'Loading...' : 'Show more results'}
            </button>
          )}
        </>
      )}

      {!searched && !loading && (
        <div className="text-center py-12">
          <p className="text-slate-500 text-sm">Search across agenda items, officials, commissions, and vote explanations.</p>
          <p className="text-slate-400 text-xs mt-1">Try &ldquo;housing&rdquo;, &ldquo;chevron&rdquo;, or a council member&apos;s name.</p>
        </div>
      )}
    </div>
  )
}
