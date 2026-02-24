import Link from 'next/link'
import type { CommissionWithStats } from '@/lib/types'

function typeBadgeColor(type: string): string {
  switch (type) {
    case 'charter': return 'bg-blue-100 text-blue-800'
    case 'regulatory': return 'bg-purple-100 text-purple-800'
    case 'advisory': return 'bg-slate-100 text-slate-700'
    default: return 'bg-slate-100 text-slate-600'
  }
}

export default function CommissionCard({ commission }: { commission: CommissionWithStats }) {
  const { id, name, commission_type, num_seats, member_count, vacancy_count, form700_required } = commission

  return (
    <Link
      href={`/commissions/${id}`}
      className="block border border-slate-200 rounded-lg p-4 hover:border-civic-navy-light hover:shadow-sm transition-all"
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <h3 className="font-semibold text-slate-900 leading-tight">{name}</h3>
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full whitespace-nowrap ${typeBadgeColor(commission_type)}`}>
          {commission_type}
        </span>
      </div>
      <div className="flex items-center gap-3 text-sm text-slate-500">
        <span>
          {member_count}{num_seats ? `/${num_seats}` : ''} seats
        </span>
        {vacancy_count > 0 && (
          <span className="text-amber-600 font-medium">
            {vacancy_count} vacant
          </span>
        )}
        {form700_required && (
          <span className="text-xs bg-amber-50 text-amber-700 px-1.5 py-0.5 rounded">
            Form 700
          </span>
        )}
      </div>
    </Link>
  )
}
