'use client'

import { Analytics } from '@vercel/analytics/next'
import { sanitizeAnalyticsEvent } from '@/lib/analytics-privacy'

/** Privacy-preserving aggregate page analytics. No custom events or IDs. */
export default function PrivacyAnalytics() {
  return <Analytics beforeSend={sanitizeAnalyticsEvent} />
}
