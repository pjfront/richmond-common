'use client'

import { Analytics } from '@vercel/analytics/next'
import { useOperatorMode } from './OperatorModeProvider'
import {
  sanitizeAnalyticsEvent,
  shouldMountAnalytics,
} from '@/lib/analytics-privacy'

/** Privacy-preserving aggregate page analytics. No custom events or IDs. */
export default function PrivacyAnalytics() {
  const { isOperator, isOperatorResolved } = useOperatorMode()

  if (!shouldMountAnalytics(isOperatorResolved, isOperator)) return null

  return <Analytics beforeSend={sanitizeAnalyticsEvent} />
}
