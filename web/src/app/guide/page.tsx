import type { Metadata } from 'next'
import Richmond101Content from '@/components/Richmond101Content'

export const metadata: Metadata = {
  title: 'How to Follow Richmond City Government',
  description:
    'Find Richmond, California meetings, read agendas, follow council votes, speak during public comment, and learn about boards and commissions.',
  alternates: {
    canonical: '/guide',
  },
}

export default function CityGovernmentGuidePage() {
  return <Richmond101Content />
}
