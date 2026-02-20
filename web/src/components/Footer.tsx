import Link from 'next/link'
import SubmitTipButton from './SubmitTipButton'

export default function Footer() {
  return (
    <footer className="bg-slate-800 text-slate-300 mt-auto">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex flex-col sm:flex-row justify-between items-start gap-4">
          <div>
            <p className="font-semibold text-white">Richmond Transparency Project</p>
            <p className="text-sm mt-1">
              AI-powered local government accountability for Richmond, CA.
            </p>
            <p className="text-xs mt-2 text-slate-400">
              Not affiliated with the City of Richmond.
            </p>
          </div>
          <div className="flex gap-6 text-sm">
            <Link href="/about" className="hover:text-white transition-colors">
              Methodology
            </Link>
            <Link href="/about#data-sources" className="hover:text-white transition-colors">
              Data Sources
            </Link>
            <a
              href="https://www.transparentrichmond.org"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-white transition-colors"
            >
              Open Data Portal
            </a>
            <SubmitTipButton />
          </div>
        </div>
      </div>
    </footer>
  )
}
