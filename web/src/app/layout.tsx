import type { Metadata } from "next"
import { Inter } from "next/font/google"
import { NuqsAdapter } from "nuqs/adapters/next/app"
import Nav, { type NextElectionLink } from "@/components/Nav"
import Footer from "@/components/Footer"
import FloatingFeedbackButton from "@/components/FloatingFeedbackButton"
import { OperatorModeProvider } from "@/components/OperatorModeProvider"
import { FeedbackModalProvider } from "@/components/FeedbackModal"
import PrivacyAnalytics from "@/components/PrivacyAnalytics"
import { getFrontDoorElection, electionToSlug } from "@/lib/queries"
import { serializeJsonLd, siteStructuredData } from "@/lib/structured-data"
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

interface NextElectionResolution {
  link: NextElectionLink | null
  unavailable: boolean
}

/** Resolve the same provenance-gated election record used by the homepage. */
async function resolveNextElectionLink(): Promise<NextElectionResolution> {
  const result = await getFrontDoorElection()
  if (result.state !== 'ready') {
    return { link: null, unavailable: result.state === 'error' }
  }
  const election = result.data
  const year = election.election_date.slice(0, 4)
  const typeLabel = election.election_type
    .charAt(0).toUpperCase() + election.election_type.slice(1)
  return {
    link: {
      slug: electionToSlug(election),
      label: `${year} ${typeLabel}`,
    },
    unavailable: false,
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
          id="site-structured-data"
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: serializeJsonLd(siteStructuredData()) }}
        />
        <a
          href="#main-content"
          className="sr-only z-[100] min-h-11 items-center rounded-md bg-white px-4 py-2 font-semibold text-civic-navy shadow-lg focus:fixed focus:left-4 focus:top-4 focus:not-sr-only focus:inline-flex focus:outline-none focus:ring-2 focus:ring-civic-navy focus:ring-offset-2"
        >
          Skip to main content
        </a>
        <NuqsAdapter>
          <OperatorModeProvider>
            <FeedbackModalProvider>
              <Nav
                nextElection={nextElection.link}
                electionUnavailable={nextElection.unavailable}
              />
              <main id="main-content" tabIndex={-1} className="flex-1">{children}</main>
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
