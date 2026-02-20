export default function LastUpdated() {
  const now = new Date()
  const formatted = now.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  })

  return (
    <p className="text-xs text-slate-400 mt-8">
      Page generated: {formatted}
    </p>
  )
}
