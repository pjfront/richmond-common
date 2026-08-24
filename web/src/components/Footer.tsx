import Link from 'next/link'
import SubmitTipButton from './SubmitTipButton'
import packageJson from '../../package.json'

export default function Footer() {
  return (
    <footer className="mt-auto bg-slate-800 text-slate-300">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="flex flex-col justify-between gap-6 lg:flex-row lg:items-start">
          <div>
            <p className="font-semibold text-white">Richmond Commons</p>
            <p className="mt-1 text-sm">
              Your city government, in one place and in plain language.
            </p>
            <p className="mt-2 text-xs text-slate-400">
              Not affiliated with the City of Richmond.
            </p>
            <p className="mt-1 text-xs text-slate-500">
              v{packageJson.version}
            </p>
          </div>
          <nav
            aria-label="More Richmond Commons links"
            className="grid grid-cols-2 gap-x-5 text-sm sm:grid-cols-3"
          >
            <Link href="/meetings" className="inline-flex min-h-11 items-center transition-colors hover:text-white">
              Meetings
            </Link>
            <Link href="/topics" className="inline-flex min-h-11 items-center transition-colors hover:text-white">
              Topics
            </Link>
            <Link href="/meetings/most-discussed" className="inline-flex min-h-11 items-center transition-colors hover:text-white">
              Most Discussed
            </Link>
            <Link href="/council" className="inline-flex min-h-11 items-center transition-colors hover:text-white">
              Council
            </Link>
            <Link href="/elections/find-my-district" className="inline-flex min-h-11 items-center transition-colors hover:text-white">
              Find My District
            </Link>
            <Link href="/pac" className="inline-flex min-h-11 items-center transition-colors hover:text-white">
              Political Committees
            </Link>
            <Link href="/unions" className="inline-flex min-h-11 items-center transition-colors hover:text-white">
              Unions
            </Link>
            <Link href="/corporations" className="inline-flex min-h-11 items-center transition-colors hover:text-white">
              Corporations
            </Link>
            <Link href="/subscribe?source=footer" className="inline-flex min-h-11 items-center transition-colors hover:text-white">
              Stay informed
            </Link>
            <Link href="/about" className="inline-flex min-h-11 items-center transition-colors hover:text-white">
              About
            </Link>
            <Link href="/about#privacy" className="inline-flex min-h-11 items-center transition-colors hover:text-white">
              Privacy
            </Link>
            <a
              href="https://www.transparentrichmond.org"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex min-h-11 items-center transition-colors hover:text-white"
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
