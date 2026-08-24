import { notFound } from 'next/navigation'
import { isOperatorAuthenticated } from './operator-auth'

/**
 * Stop an operator-only page before it starts server-side data work for an
 * anonymous request. Client-side OperatorGate remains the presentation layer;
 * this is the fail-closed server boundary.
 */
export async function requireOperatorPage(): Promise<void> {
  if (await isOperatorAuthenticated()) return
  notFound()
}
