import type { DepartmentCompliance } from '@/lib/types'

function rateColor(rate: number): string {
  if (rate >= 80) return 'text-emerald-600'
  if (rate >= 50) return 'text-amber-600'
  return 'text-red-600'
}

export default function DepartmentBreakdown({ departments }: { departments: DepartmentCompliance[] }) {
  if (departments.length === 0) {
    return <p className="text-slate-500">No department data available.</p>
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left">
            <th className="py-3 pr-4 font-semibold text-slate-700">Department</th>
            <th className="py-3 px-4 font-semibold text-slate-700 text-right">Requests</th>
            <th className="py-3 px-4 font-semibold text-slate-700 text-right">Avg Days</th>
            <th className="py-3 px-4 font-semibold text-slate-700 text-right">On-Time %</th>
            <th className="py-3 pl-4 font-semibold text-slate-700 text-right">Slowest</th>
          </tr>
        </thead>
        <tbody>
          {departments.map((dept) => (
            <tr key={dept.department} className="border-b border-slate-100 hover:bg-slate-50">
              <td className="py-3 pr-4 font-medium text-slate-800">{dept.department}</td>
              <td className="py-3 px-4 text-right text-slate-600">{dept.requestCount}</td>
              <td className="py-3 px-4 text-right text-slate-600">{dept.avgDays}</td>
              <td className={`py-3 px-4 text-right font-medium ${rateColor(dept.onTimeRate)}`}>
                {dept.onTimeRate}%
              </td>
              <td className="py-3 pl-4 text-right text-slate-500">{dept.slowestDays} days</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
