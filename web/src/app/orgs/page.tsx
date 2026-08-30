/**
 * Legacy /orgs redirect while campaign directories are held through T14.
 */

import type { Metadata } from 'next'
import { redirect } from 'next/navigation'

export const metadata: Metadata = {
  robots: { index: false, follow: false },
}

export default function OrgsRedirect() {
  redirect('/elections')
}
