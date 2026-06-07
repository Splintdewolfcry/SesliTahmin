function formatPrice(price: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(price)
}

interface PriceDisplayProps {
  price: number
  changePercent: number | null
  direction?: 'up' | 'down' | 'neutral'
}

export default function PriceDisplay({ price, changePercent, direction }: PriceDisplayProps) {
  const arrow = direction === 'up' ? '↑' : direction === 'down' ? '↓' : ''

  return (
    <div className="flex items-baseline gap-2">
      <span className="text-white font-medium">{formatPrice(price)}</span>
      {changePercent != null && (
        <span
          className={`text-xs font-mono ${changePercent >= 0 ? 'text-green-400' : 'text-red-400'}`}
        >
          {changePercent >= 0 ? '+' : ''}
          {changePercent.toFixed(2)}%
        </span>
      )}
      {arrow && (
        <span
          className={`text-sm ${direction === 'up' ? 'text-green-400' : direction === 'down' ? 'text-red-400' : 'text-zinc-400'}`}
        >
          {arrow}
        </span>
      )}
    </div>
  )
}