import Link from 'next/link'
import SubmitTipButton from './SubmitTipButton'
import packageJson from '../../package.json'

export default function Footer() {
  return (
    <footer className="bg-slate-800 text-slate-300 mt-auto">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex flex-col justify-between gap-6 lg:flex-row lg:items-start">
          <div>
            <p className="font-semibold text-white">Richmond Commons</p>
            <p className="text-sm mt-1">
              Your city government, in one place and in plain language.
            </p>
            <p className="text-xs mt-2 text-slate-400">
              Not affiliated with the City of Richmond.
            </p>
            <p className="text-xs mt-1 text-slate-500">
              v{packageJson.version}
            </p>
          </div>
          <nav aria-label="More Richmond Commons links" className="grid grid-cols-2 gap-x-5 text-sm sm:grid-cols-3">
            <Link href="/meetings" className="inline-flex min-h-11 items-center hover:text-white transition-colors">
              Meetings
            </Link>
            <Link href="/topics" className="inline-flex min-h-11 items-center hover:text-white transition-colors">
              Topics
            </Link>
            <Link href="/meetings/most-discussed" className="inline-flex min-h-11 items-center hover:text-white transition-colors">
              Most Discussed
            </Link>
            <Link href="/council" className="inline-flex min-h-11 items-center hover:text-white transition-colors">
              Council
            </Link>
            <Link href="/elections/find-my-district" className="inline-flex min-h-11 items-center hover:text-white transition-colors">
              Find My District
            </Link>
            <Link href="/pac" className="inline-flex min-h-11 items-center hover:text-white transition-colors">
              Political Committees
            </Link>
            <Link href="/unions" className="inline-flex min-h-11 items-center hover:text-white transition-colors">
              Unions
            </Link>
            <Link href="/corporations" className="inline-flex min-h-11 items-center hover:text-white transition-colors">
              Corporations
            </Link>
            <Link
              href="/subscribe?source=footer"
              className="inline-flex min-h-11 items-center hover:text-white transition-colors"
            >
              Stay informed
            </Link>
            <Link href="/about" className="inline-flex min-h-11 items-center hover:text-white transition-colors">
              About
            </Link>
            <a
              href="https://www.transparentrichmond.org"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex min-h-11 items-center hover:text-white transition-colors"
            >
              Open Data Portal
            </a>
            <SubmitTipButton />
          </nav>
        </div>
      </div>
    </footer>
  )
}
