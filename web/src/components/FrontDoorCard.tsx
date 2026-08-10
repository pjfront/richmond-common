import Link from 'next/link'
import type { ReactNode } from 'react'

interface FrontDoorCardProps {
  href: string
  eyebrow: string
  title: string
  description: string
  children?: ReactNode
}

export default function FrontDoorCard({
  href,
  eyebrow,
  title,
  description,
  children,
}: FrontDoorCardProps) {
  return (
    <Link
      href={href}
      className="group flex min-h-52 flex-col rounded-lg border border-slate-200 bg-white p-5 shadow-sm transition-all hover:border-civic-navy-light hover:shadow-md focus:outline-none focus:ring-2 focus:ring-civic-navy focus:ring-offset-2"
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-civic-navy-light">
        {eyebrow}
      </p>
      <h3 className="mt-2 text-xl font-bold text-slate-900 group-hover:text-civic-navy">
        {title}
      </h3>
      <p className="mt-2 text-sm leading-relaxed text-slate-600">{description}</p>
      <div className="mt-auto pt-5">
        {children ?? (
          <span className="text-sm font-semibold text-civic-navy" aria-hidden="true">
            View details &rarr;
          </span>
        )}
      </div>
    </Link>
  )
}
