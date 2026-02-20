import type { MeetingAttendance, Official } from '@/lib/types'

type AttendanceEntry = MeetingAttendance & { official: Pick<Official, 'name' | 'role'> }

const statusDot: Record<string, string> = {
  present: 'bg-vote-aye',
  absent: 'bg-vote-absent',
  late: 'bg-civic-amber',
}

const statusLabel: Record<string, string> = {
  present: 'Present',
  absent: 'Absent',
  late: 'Late',
}

export default function AttendanceRoster({ attendance }: { attendance: AttendanceEntry[] }) {
  if (attendance.length === 0) return null

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <h3 className="text-sm font-semibold text-slate-700 mb-3">Attendance</h3>
      <div className="flex flex-wrap gap-3">
        {attendance.map((a) => (
          <div key={a.id} className="flex items-center gap-2">
            <span className={`w-2.5 h-2.5 rounded-full ${statusDot[a.status] ?? 'bg-slate-300'}`} />
            <span className="text-sm text-slate-700">{a.official.name}</span>
            <span className="text-xs text-slate-400">({statusLabel[a.status] ?? a.status})</span>
          </div>
        ))}
      </div>
    </div>
  )
}
