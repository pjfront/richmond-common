import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import { NuqsAdapter } from 'nuqs/adapters/next/app'
import StageHeader from '@/components/StageHeader'
import StageFooter from '@/components/StageFooter'
import { CivicLanguageProvider } from '@/components/civic/CivicLanguage'
import Nav from '@/components/Nav'
import { OperatorModeProvider } from '@/components/OperatorModeProvider'
import { isLocalArchive } from '@/lib/feature-policy'
import './globals.css'

export const revalidate = 86400

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' })

export const metadata: Metadata = {
  title: isLocalArchive()
    ? { default: 'Richmond Commons · Local archive', template: '%s | Richmond Commons local archive' }
    : { default: 'Richmond Commons · Private preview', template: '%s | Richmond Commons preview' },
  description: 'A private preview of search across Richmond agenda items, recorded votes, and reported campaign money.',
  robots: { index: false, follow: false, noarchive: true, nosnippet: true },
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const local = isLocalArchive()
  const content = <>
    {local ? <Nav /> : <StageHeader />}
    {local && <div className="border-b border-slate-200 bg-slate-50 px-4 py-3 text-center text-sm text-slate-700">
      Local archive · Saved records · Paid AI and email off · <a href="/library" className="font-medium underline">Browse all tools</a>
    </div>}
    <main id="main-content" tabIndex={-1} className="flex-1">{children}</main>
    <StageFooter local={local} />
  </>
  return (
    <html lang="en">
      <body className={`${inter.variable} flex min-h-screen flex-col antialiased`}>
        <NuqsAdapter>
          <CivicLanguageProvider>
            {local ? <OperatorModeProvider>{content}</OperatorModeProvider> : content}
          </CivicLanguageProvider>
        </NuqsAdapter>
      </body>
    </html>
  )
}
