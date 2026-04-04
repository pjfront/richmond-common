import type { Metadata } from "next"
import { Inter } from "next/font/google"
import { NuqsAdapter } from "nuqs/adapters/next/app"
import Nav from "@/components/Nav"
import UpcomingMeetingBanner from "@/components/UpcomingMeetingBanner"
import Footer from "@/components/Footer"
import FloatingFeedbackButton from "@/components/FloatingFeedbackButton"
import { OperatorModeProvider } from "@/components/OperatorModeProvider"
import { FeedbackModalProvider } from "@/components/FeedbackModal"
import "./globals.css"

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

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} antialiased flex flex-col min-h-screen`}>
        <NuqsAdapter>
          <OperatorModeProvider>
            <FeedbackModalProvider>
              <Nav />
              <UpcomingMeetingBanner />
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
