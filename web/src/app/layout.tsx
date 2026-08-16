import type { Metadata } from "next"
import { Inter } from "next/font/google"
import { NuqsAdapter } from "nuqs/adapters/next/app"
import Nav, { type NextElectionLink } from "@/components/Nav"
import Footer from "@/components/Footer"
import FloatingFeedbackButton from "@/components/FloatingFeedbackButton"
import { OperatorModeProvider } from "@/components/OperatorModeProvider"
import { FeedbackModalProvider } from "@/components/FeedbackModal"
import PrivacyAnalytics from "@/components/PrivacyAnalytics"
import { getUpcomingElection, electionToSlug } from "@/lib/queries"
import { serializeJsonLd, siteStructuredData } from "@/lib/structured-data"
import "./globals.css"

// Project-wide ISR default. Individual routes may opt into a longer bounded
// cadence when their data and invalidation behavior justify it.
export const revalidate = 3600

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
  // Reduce referrer detail Richmond Commons sends on later navigation. The
  // policy cannot control the detail an external source sends on arrival.
  referrer: "strict-origin",
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
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: serializeJsonLd(siteStructuredData()) }}
        />
        <NuqsAdapter>
          <OperatorModeProvider>
            <FeedbackModalProvider>
              <Nav nextElection={nextElection} />
              <main className="flex-1">{children}</main>
              <Footer />
              <FloatingFeedbackButton />
            </FeedbackModalProvider>
            <PrivacyAnalytics />
          </OperatorModeProvider>
        </NuqsAdapter>
      </body>
    </html>
  )
}
