import { useNavigate } from 'react-router-dom'
import { formatDistanceToNow } from 'date-fns'
import type { Prediction, PriceQuote } from '../types'

function formatPrice(price: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(price)
}

function formatPercent(change: number): string {
  return (change >= 0 ? '+' : '') + change.toFixed(2) + '%'
}

interface PredictionCardProps {
  prediction: Prediction
  prices: Record<string, PriceQuote>
}

export default function PredictionCard({ prediction, prices }: PredictionCardProps) {
  const navigate = useNavigate()

  const CHECKIN_ORDER = ['15min', '45min', '1h', '6h', '12h', '1d', '3d', '1w']

  const directionSymbol =
    prediction.direction === 'up' ? '↑' : prediction.direction === 'down' ? '↓' : '→'

  const directionColor =
    prediction.direction === 'up'
      ? 'text-green-400'
      : prediction.direction === 'down'
        ? 'text-red-400'
        : 'text-zinc-400'

  const currentPrice = prices[prediction.asset]?.price ?? null

  const pctChange =
    currentPrice != null
      ? ((currentPrice - prediction.entry_price) / prediction.entry_price) * 100
      : null

  const hasCheckins = Object.keys(prediction.checkins).length > 0

  const lastCheckinPrice = hasCheckins
    ? (() => {
        for (let i = CHECKIN_ORDER.length - 1; i >= 0; i--) {
          const c = prediction.checkins[CHECKIN_ORDER[i]]
          if (c?.price != null) return c.price
        }
        return null
      })()
    : null

  const displayPrice = lastCheckinPrice ?? currentPrice

  const timeAgo = formatDistanceToNow(new Date(prediction.created_at), { addSuffix: true })

  const targetProgress =
    prediction.target_price != null && prediction.entry_price != null
      ? (() => {
          const total = Math.abs(prediction.target_price - prediction.entry_price)
          if (total === 0) return null
          const current = displayPrice ?? prediction.entry_price
          const moved = Math.abs(current - prediction.entry_price)
          return Math.min(Math.round((moved / total) * 100), 100)
        })()
      : null

  return (
    <div
      onClick={() => navigate(`/predictions/${prediction.id}`)}
      className="bg-zinc-800 border border-zinc-700 rounded-lg p-4 cursor-pointer hover:border-zinc-500 transition-colors"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-lg font-bold text-white">{prediction.asset}</span>
          <span className={`text-lg font-bold ${directionColor}`}>{directionSymbol}</span>
          {prediction.target_price != null && (
            <span className="text-xs text-zinc-400">
              Target: {formatPrice(prediction.target_price)}
            </span>
          )}
        </div>
        <span className="text-xs text-zinc-500">{timeAgo}</span>
      </div>

      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-zinc-400">
          Entry: {formatPrice(prediction.entry_price)}
        </span>
        {displayPrice != null && (
          <span className="text-sm text-white">
            {formatPrice(displayPrice)}
            {pctChange != null && (
              <span
                className={`ml-1 text-xs ${pctChange >= 0 ? 'text-green-400' : 'text-red-400'}`}
              >
                {formatPercent(pctChange)}
              </span>
            )}
          </span>
        )}
      </div>

      <div className="flex gap-1 mb-2">
        {CHECKIN_ORDER.map((mark) => {
          const checkin = prediction.checkins[mark]
          const dueAt = new Date(checkin?.due_at ?? '')
          const isDue = dueAt <= new Date()
          const isFilled = checkin?.price != null
          let dotColor = 'bg-zinc-600'
          if (isFilled) {
            const change =
              ((checkin!.price! - prediction.entry_price) / prediction.entry_price) * 100
            dotColor = change >= 0 ? 'bg-green-400' : 'bg-red-400'
          } else if (isDue) {
            dotColor = 'bg-zinc-500'
          }
          return (
            <div key={mark} className="flex-1 flex flex-col items-center gap-1">
              <div
                className={`w-2 h-2 rounded-full ${dotColor} ${!isFilled && isDue ? 'ring-1 ring-zinc-400' : ''}`}
              />
              <span className="text-[10px] text-zinc-500">{mark}</span>
            </div>
          )
        })}
      </div>

      {targetProgress != null && (
        <div className="w-full bg-zinc-700 rounded-full h-1">
          <div
            className="bg-blue-500 rounded-full h-1 transition-all"
            style={{ width: `${targetProgress}%` }}
          />
        </div>
      )}
    </div>
  )
}