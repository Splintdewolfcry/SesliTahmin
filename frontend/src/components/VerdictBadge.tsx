interface VerdictBadgeProps {
  verdict: { status: 'hit' | 'partial' | 'miss' | 'pending'; pctChange?: number }
}

export default function VerdictBadge({ verdict }: VerdictBadgeProps) {
  const styles: Record<string, string> = {
    hit: 'bg-green-900/50 text-green-400 border-green-700',
    partial: 'bg-yellow-900/50 text-yellow-400 border-yellow-700',
    miss: 'bg-red-900/50 text-red-400 border-red-700',
    pending: 'bg-zinc-800 text-zinc-400 border-zinc-600',
  }

  const labels: Record<string, string> = {
    hit: 'Hit',
    partial: 'Partial',
    miss: 'Miss',
    pending: 'Pending',
  }

  return (
    <span
      className={`px-2 py-0.5 rounded text-xs font-medium border ${styles[verdict.status]}`}
    >
      {labels[verdict.status]}
      {verdict.pctChange != null ? ` (${verdict.pctChange >= 0 ? '+' : ''}${verdict.pctChange.toFixed(1)}%)` : ''}
    </span>
  )
}