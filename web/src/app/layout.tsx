import type { Metadata } from "next"
import { Inter } from "next/font/google"
import Nav from "@/components/Nav"
import Footer from "@/components/Footer"
import "./globals.css"

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
})

export const metadata: Metadata = {
  title: {
    default: "Richmond Transparency Project",
    template: "%s | Richmond Transparency",
  },
  description:
    "AI-powered local government accountability for Richmond, CA. Track council votes, campaign contributions, and conflicts of interest.",
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} antialiased flex flex-col min-h-screen`}>
        <Nav />
        <main className="flex-1">{children}</main>
        <Footer />
      </body>
    </html>
  )
}
