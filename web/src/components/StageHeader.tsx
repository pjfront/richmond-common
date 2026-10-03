import Link from 'next/link'

const navigation = [
  { href: '/search', label: 'Search' },
  { href: '/meetings', label: 'Meetings' },
  { href: '/money', label: 'Money' },
] as const

export default function StageHeader() {
  return (
    <header className="border-b border-slate-200 bg-white">
      <a href="#main-content" className="sr-only z-50 rounded-md bg-civic-navy text-white focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:min-h-11 focus:px-4 focus:py-3">Skip to content</a>
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-6 gap-y-3 px-4 py-4 sm:px-6 lg:px-8">
        <Link href="/" className="inline-flex min-h-11 flex-col justify-center text-civic-navy">
          <span className="text-xl font-bold tracking-tight">Richmond Commons</span>
          <span className="text-sm text-slate-600">Richmond, California</span>
        </Link>
        <span className="inline-flex min-h-11 items-center rounded-full border border-amber-200 bg-amber-50 px-3 text-sm font-semibold text-amber-900">Private preview</span>
        <div className="grid w-full items-center gap-x-6 gap-y-3 sm:grid-cols-[auto_minmax(0,1fr)] lg:w-auto lg:grid-cols-[auto_18rem]">
          <nav aria-label="Main navigation" className="flex items-center gap-1">
            {navigation.map(({ href, label }) => <Link key={href} href={href} className="inline-flex min-h-11 min-w-11 items-center rounded-md px-3 font-medium text-civic-navy hover:bg-slate-100">{label}</Link>)}
          </nav>
          <form action="/search" method="get" role="search" aria-label="Search the public record" className="flex min-w-0 gap-2">
            <label htmlFor="header-search" className="sr-only">Search a name or topic</label>
            <input id="header-search" name="q" type="search" maxLength={200} placeholder="Name or topic" className="min-h-11 w-full min-w-0 rounded-md border border-slate-500 px-3 text-base focus:outline-2 focus:outline-offset-2 focus:outline-civic-navy" />
            <button type="submit" className="min-h-11 shrink-0 rounded-md bg-civic-navy px-4 font-medium text-white hover:bg-civic-navy-light">Search</button>
          </form>
        </div>
      </div>
    </header>
  )
}
