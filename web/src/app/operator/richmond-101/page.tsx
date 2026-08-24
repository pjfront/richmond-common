import type { Metadata } from 'next'
import Richmond101Content from '@/components/Richmond101Content'

export const metadata: Metadata = {
  title: 'Richmond 101 Draft',
  description: 'Operator-only voice-review draft for the Richmond 101 guide.',
  robots: {
    index: false,
    follow: false,
    noarchive: true,
    nosnippet: true,
  },
}

export default function OperatorRichmond101Page() {
  return <Richmond101Content />
}
