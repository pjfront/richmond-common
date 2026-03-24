import Link from 'next/link'

export default function NotFound() {
  return (
    <div className="max-w-2xl mx-auto px-4 py-20 text-center">
      <h1 className="text-4xl font-bold text-civic-navy mb-4">Page not found</h1>
      <p className="text-lg text-slate-600 mb-8">
        The page you are looking for does not exist or may have been moved.
      </p>
      <div className="flex flex-wrap justify-center gap-4">
        <Link
          href="/"
          className="px-5 py-2.5 bg-civic-navy text-white rounded-lg hover:bg-civic-navy-light transition-colors"
        >
          Go home
        </Link>
        <Link
          href="/meetings"
          className="px-5 py-2.5 border border-civic-navy/30 text-civic-navy rounded-lg hover:bg-civic-navy/5 transition-colors"
        >
          Browse meetings
        </Link>
        <Link
          href="/council"
          className="px-5 py-2.5 border border-civic-navy/30 text-civic-navy rounded-lg hover:bg-civic-navy/5 transition-colors"
        >
          View council
        </Link>
      </div>
    </div>
  )
}
