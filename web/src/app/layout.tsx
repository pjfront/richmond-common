import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import { NuqsAdapter } from 'nuqs/adapters/next/app'
import StageHeader from '@/components/StageHeader'
import StageFooter from '@/components/StageFooter'
import { CivicLanguageProvider } from '@/components/civic/CivicLanguage'
import './globals.css'

export const revalidate = 86400

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' })

export const metadata: Metadata = {
  title: { default: 'Richmond Commons · Private preview', template: '%s | Richmond Commons preview' },
  description: 'A private preview of search across Richmond agenda items, recorded votes, and reported campaign money.',
  robots: { index: false, follow: false, noarchive: true, nosnippet: true },
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} flex min-h-screen flex-col antialiased`}>
        <NuqsAdapter>
          <CivicLanguageProvider>
            <StageHeader />
            <main id="main-content" tabIndex={-1} className="flex-1">{children}</main>
            <StageFooter />
          </CivicLanguageProvider>
        </NuqsAdapter>
      </body>
    </html>
  )
}
