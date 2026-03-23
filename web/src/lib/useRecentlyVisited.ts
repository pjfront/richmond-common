'use client'

import { useState, useEffect, useCallback } from 'react'
import type { EntityType } from '@/lib/types'

export interface VisitedEntity {
  type: EntityType
  id: string
  title: string
  url: string
  visitedAt: number
}

const STORAGE_KEY = 'richmond-common-recently-visited'
const MAX_ENTRIES = 8

function readFromStorage(): VisitedEntity[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    // Basic shape validation
    return parsed.filter(
      (e): e is VisitedEntity =>
        typeof e === 'object' &&
        e !== null &&
        typeof e.type === 'string' &&
        typeof e.id === 'string' &&
        typeof e.title === 'string' &&
        typeof e.url === 'string' &&
        typeof e.visitedAt === 'number'
    )
  } catch {
    return []
  }
}

function writeToStorage(entities: VisitedEntity[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entities))
  } catch {
    // Silently fail — quota exceeded or private mode
  }
}

export function useRecentlyVisited() {
  const [visits, setVisits] = useState<VisitedEntity[]>([])

  // Hydrate on mount (SSR-safe)
  useEffect(() => {
    setVisits(readFromStorage())
  }, [])

  const addVisit = useCallback((entity: VisitedEntity) => {
    setVisits((prev) => {
      const deduped = prev.filter(
        (e) => !(e.type === entity.type && e.id === entity.id)
      )
      const updated = [entity, ...deduped].slice(0, MAX_ENTRIES)
      writeToStorage(updated)
      return updated
    })
  }, [])

  const clearVisits = useCallback(() => {
    setVisits([])
    writeToStorage([])
  }, [])

  return { visits, addVisit, clearVisits }
}
