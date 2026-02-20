const styles: Record<string, string> = {
  aye: 'bg-vote-aye/10 text-vote-aye border-vote-aye/20',
  nay: 'bg-vote-nay/10 text-vote-nay border-vote-nay/20',
  abstain: 'bg-vote-abstain/10 text-vote-abstain border-vote-abstain/20',
  absent: 'bg-vote-absent/10 text-vote-absent border-vote-absent/20',
}

export default function VoteBadge({ choice }: { choice: string }) {
  const normalized = choice.toLowerCase()
  return (
    <span
      className={`inline-block text-xs font-semibold px-2 py-0.5 rounded border ${styles[normalized] ?? 'bg-slate-100 text-slate-600 border-slate-200'}`}
    >
      {choice}
    </span>
  )
}
