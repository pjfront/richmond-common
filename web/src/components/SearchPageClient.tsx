'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { useSearchParams } from 'next/navigation'
import type { SearchResult, SearchResponse } from '@/lib/types'
import SearchResultCard from './SearchResultCard'

const DEBOUNCE_MS = 300
const PAGE_SIZE = 20

export default function SearchPageClient() {
  const searchParams = useSearchParams()
  const initialQuery = searchParams.get('q') ?? ''

  const [query, setQuery] = useState(initialQuery)
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [totalLoaded, setTotalLoaded] = useState(0)
  const [searched, setSearched] = useState(false)

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const doSearch = useCallback(async (q: string, offset: number, append: boolean) => {
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

    const params = new URLSearchParams({ q, limit: String(PAGE_SIZE), offset: String(offset), type: 'agenda_item' })

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
      doSearch(query, 0, false)
      // Sync URL for shareable links
      const url = query.length >= 2
        ? `${window.location.pathname}?q=${encodeURIComponent(query)}`
        : window.location.pathname
      window.history.replaceState(null, '', url)
    }, DEBOUNCE_MS)

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [query, doSearch])

  const loadMore = () => {
    doSearch(query, totalLoaded, true)
  }

  return (
    <div>
      {/* Search input */}
      <div className="mb-4">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search agenda items..."
          className="w-full px-4 py-3 rounded-lg border border-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-civic-navy/30 focus:border-civic-navy"
          autoFocus
        />
      </div>

      {/* Results */}
      {loading && results.length === 0 && (
        <p className="text-sm text-slate-500 py-8 text-center">Searching...</p>
      )}

      {searched && !loading && results.length === 0 && (
        <div className="text-center py-12">
          <p className="text-slate-600 text-sm">No results found for &ldquo;{query}&rdquo;</p>
          <p className="text-slate-400 text-xs mt-1">Try different keywords.</p>
        </div>
      )}

      {results.length > 0 && (
        <>
          <p className="text-xs text-slate-400 mb-3">
            {totalLoaded} result{totalLoaded !== 1 ? 's' : ''} for &ldquo;{query}&rdquo;
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
          <p className="text-slate-500 text-sm">Search Richmond city council agenda items.</p>
          <p className="text-slate-400 text-xs mt-1">Try &ldquo;housing&rdquo;, &ldquo;chevron&rdquo;, or &ldquo;police&rdquo;.</p>
        </div>
      )}
    </div>
  )
}
