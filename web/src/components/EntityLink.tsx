'use client'

import Link from 'next/link'

/**
 * EntityLink — renders an entity name as a link to its profile page
 * when a URL is found in the provided lookup map, otherwise renders
 * plain text.
 *
 * S28.5 cross-linking pass. The urlMap is built at the page level
 * (server component) and passed down. When new entity types graduate
 * to public (orgs, candidates), their URLs appear in the map and
 * cross-links activate automatically — no component changes needed.
 */
interface EntityLinkProps {
  name: string
  /** Normalized-name → profile URL. Null = no linking (plain text). */
  urlMap: Map<string, string> | null
  className?: string
}

export default function EntityLink({ name, urlMap, className }: EntityLinkProps) {
  const url = urlMap?.get(name.toLowerCase().trim())
  if (!url) return <span className={className}>{name}</span>
  return (
    <Link href={url} className={className}>
      {name}
    </Link>
  )
}
