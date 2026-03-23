'use client'

import { useEffect } from 'react'
import { useRecentlyVisited } from '@/lib/useRecentlyVisited'
import type { EntityType } from '@/lib/types'

interface RecordVisitProps {
  type: EntityType
  id: string
  title: string
  url: string
}

export default function RecordVisit({ type, id, title, url }: RecordVisitProps) {
  const { addVisit } = useRecentlyVisited()

  useEffect(() => {
    addVisit({ type, id, title, url, visitedAt: Date.now() })
  }, [type, id]) // eslint-disable-line react-hooks/exhaustive-deps

  return null
}
