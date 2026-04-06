import type { Metadata } from 'next'
import OperatorSettingsPage from './OperatorSettingsPage'

export const metadata: Metadata = {
  title: 'Operator Settings',
  description: 'Configure AI scoring parameters for the conflict scanner.',
}

export default function SettingsPage() {
  return <OperatorSettingsPage />
}
