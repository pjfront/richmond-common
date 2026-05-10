import type { Metadata } from "next"
import { Inter } from "next/font/google"
import { NuqsAdapter } from "nuqs/adapters/next/app"
import Nav, { type NextElectionLink } from "@/components/Nav"
import Footer from "@/components/Footer"
import FloatingFeedbackButton from "@/components/FloatingFeedbackButton"
import { OperatorModeProvider } from "@/components/OperatorModeProvider"
import { FeedbackModalProvider } from "@/components/FeedbackModal"
import { getUpcomingElection, electionToSlug } from "@/lib/queries"
import "./globals.css"

// ISR default: 24h. Civic data changes weekly at most; hourly was 24x overkill
// and the dominant Vercel function-invocation + Supabase egress cost driver.
// Pipeline writes call /api/revalidate to bust caches on real data changes.
export const revalidate = 86400

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
})

const siteDescription =
  "Your city government, in one place and in plain language. Follow council votes, campaign contributions, and public meetings."

export const metadata: Metadata = {
  title: {
    default: "Richmond Commons",
    template: "%s | Richmond Commons",
  },
  description: siteDescription,
  metadataBase: new URL("https://richmondcommons.org"),
  openGraph: {
    title: "Richmond Commons",
    description: siteDescription,
    url: "https://richmondcommons.org",
    siteName: "Richmond Commons",
    locale: "en_US",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Richmond Commons",
    description: siteDescription,
  },
  robots: {
    index: true,
    follow: true,
  },
}

/** Resolve the upcoming-election link for the nav. Returns null when no
 *  election is on the calendar, in which case the Elections menu collapses
 *  to its static voter-info routes only (Find My District, etc.). */
async function resolveNextElectionLink(): Promise<NextElectionLink | null> {
  const election = await getUpcomingElection()
  if (!election) return null
  const date = new Date(election.election_date + 'T00:00:00')
  const year = date.getFullYear()
  const typeLabel = election.election_type
    .charAt(0).toUpperCase() + election.election_type.slice(1)
  const formattedDate = date.toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
  })
  return {
    slug: electionToSlug(election),
    label: `${year} ${typeLabel}`,
    description: `${formattedDate}: candidates and fundraising`,
  }
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  const nextElection = await resolveNextElectionLink()
  return (
    <html lang="en">
      <body className={`${inter.variable} antialiased flex flex-col min-h-screen`}>
        <NuqsAdapter>
          <OperatorModeProvider>
            <FeedbackModalProvider>
              <Nav nextElection={nextElection} />
              <main className="flex-1">{children}</main>
              <Footer />
              <FloatingFeedbackButton />
            </FeedbackModalProvider>
          </OperatorModeProvider>
        </NuqsAdapter>
      </body>
    </html>
  )
}
