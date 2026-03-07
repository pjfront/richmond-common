import type { Metadata } from 'next'
import OperatorDecisionsPage from './OperatorDecisionsPage'

export const metadata: Metadata = {
  title: 'Operator Decisions',
  description: 'Pending operator decisions requiring human judgment.',
}

export default function DecisionsPage() {
  return <OperatorDecisionsPage />
}
