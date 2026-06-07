import type { Checkin } from '../types'

function formatPercent(change: number): string {
  return (change >= 0 ? '+' : '') + change.toFixed(2) + '%'
}

const CHECKIN_ORDER = ['15min', '45min', '1h', '6h', '12h', '1d', '3d', '1w']

interface CheckinTimelineProps {
  checkins: Record<string, Checkin>
  entryPrice: number
}

export default function CheckinTimeline({ checkins, entryPrice }: CheckinTimelineProps) {
  return (
    <div className="space-y-2">
      {CHECKIN_ORDER.map((mark) => {
        const checkin = checkins[mark]

        if (!checkin) {
          return (
            <div key={mark} className="flex items-center gap-3 py-1">
              <div className="w-2.5 h-2.5 rounded-full bg-zinc-600" />
              <span className="text-xs text-zinc-500 w-12">{mark}</span>
              <span className="text-xs text-zinc-600">Not scheduled</span>
            </div>
          )
        }

        const isFilled = checkin.price != null
        const isDue = new Date(checkin.due_at) <= new Date()
        const pctChange = isFilled
          ? ((checkin.price! - entryPrice) / entryPrice) * 100
          : null

        let dotClass = 'bg-zinc-600'
        if (isFilled) {
          dotClass = pctChange! >= 0 ? 'bg-green-400' : 'bg-red-400'
        } else if (isDue) {
          dotClass = 'bg-zinc-500 ring-1 ring-zinc-400'
        }

        const hasError = checkin.fetch_error != null

        return (
          <div key={mark} className="flex items-center gap-3 py-1">
            <div className={`w-2.5 h-2.5 rounded-full ${dotClass}`} />
            <span className="text-xs text-zinc-400 w-12">{mark}</span>
            {isFilled ? (
              <span className="text-xs text-white font-mono">
                ${checkin.price!.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </span>
            ) : isDue ? (
              <span className="text-xs text-zinc-500">Pending</span>
            ) : (
              <span className="text-xs text-zinc-600">Not yet due</span>
            )}
            {pctChange != null && (
              <span
                className={`text-xs font-mono ${pctChange >= 0 ? 'text-green-400' : 'text-red-400'}`}
              >
                {formatPercent(pctChange)}
              </span>
            )}
            {hasError && (
              <span className="text-xs text-red-400" title={checkin.fetch_error!}>
                Fetch failed
              </span>
            )}
            {checkin.source && isFilled && (
              <span className="text-[10px] text-zinc-600">{checkin.source}</span>
            )}
          </div>
        )
      })}
    </div>
  )
}