import { useState } from 'react'
import { format } from 'date-fns'
import CheckinTimeline from './CheckinTimeline'
import VerdictBadge from './VerdictBadge'
import PredictionForm from './PredictionForm'
import type { Prediction, PriceQuote, PatchPredictionRequest } from '../types'

function formatPrice(price: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(price)
}

interface PredictionDetailProps {
  prediction: Prediction
  prices: Record<string, PriceQuote>
  onRefresh: () => void
  onEdit: (patch: PatchPredictionRequest) => Promise<void>
  onDelete: () => void
  onNavigateJournal: () => void
}

export default function PredictionDetail({
  prediction,
  prices,
  onRefresh,
  onEdit,
  onDelete,
  onNavigateJournal,
}: PredictionDetailProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [isSaving, setIsSaving] = useState(false)

  const currentPrice = prices[prediction.asset]?.price ?? null

  const computeVerdict = () => {
    const latestPrice = currentPrice
    if (latestPrice == null) return { status: 'pending' as const }
    const pctChange = ((latestPrice - prediction.entry_price) / prediction.entry_price) * 100
    const directionCorrect =
      (prediction.direction === 'up' && pctChange > 0) ||
      (prediction.direction === 'down' && pctChange < 0) ||
      (prediction.direction === 'neutral' && Math.abs(pctChange) < 1)
    const targetHit =
      prediction.target_price != null &&
      ((prediction.direction === 'up' && latestPrice >= prediction.target_price) ||
        (prediction.direction === 'down' && latestPrice <= prediction.target_price))
    if (targetHit) return { status: 'hit' as const, pctChange }
    if (directionCorrect && Math.abs(pctChange) >= 1) return { status: 'partial' as const, pctChange }
    if (!directionCorrect) return { status: 'miss' as const, pctChange }
    return { status: 'pending' as const, pctChange }
  }

  const verdict = computeVerdict()

  const handleRefresh = async () => {
    setIsRefreshing(true)
    try {
      await onRefresh()
    } finally {
      setIsRefreshing(false)
    }
  }

  const handleSave = async (patch: PatchPredictionRequest) => {
    setIsSaving(true)
    try {
      await onEdit(patch)
      setIsEditing(false)
    } finally {
      setIsSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true)
      return
    }
    await onDelete()
  }

  const directionSymbol =
    prediction.direction === 'up' ? '↑' : prediction.direction === 'down' ? '↓' : '→'

  if (isEditing) {
    return (
      <div className="space-y-4">
        <h2 className="text-lg font-bold text-white">Edit Prediction</h2>
        {isSaving ? (
          <p className="text-zinc-400">Saving...</p>
        ) : (
          <PredictionForm
            prediction={prediction}
            onSave={handleSave}
            onCancel={() => setIsEditing(false)}
          />
        )}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-2xl font-bold text-white">{prediction.asset}</span>
          <span className="text-2xl">{directionSymbol}</span>
          <VerdictBadge verdict={verdict} />
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="px-3 py-1.5 bg-zinc-700 rounded text-sm hover:bg-zinc-600 transition-colors disabled:opacity-50"
          >
            {isRefreshing ? 'Refreshing...' : 'Refresh'}
          </button>
          <button
            onClick={() => setIsEditing(true)}
            className="px-3 py-1.5 bg-zinc-700 rounded text-sm hover:bg-zinc-600 transition-colors"
          >
            Edit
          </button>
          <button
            onClick={handleDelete}
            className="px-3 py-1.5 bg-red-900/50 rounded text-sm hover:bg-red-800 transition-colors text-red-400"
          >
            {confirmDelete ? 'Confirm Delete' : 'Delete'}
          </button>
        </div>
      </div>

      <div className="bg-zinc-800/60 rounded-lg p-3">
        <p className="text-xs text-zinc-400 mb-1">Transcript</p>
        <p className="text-zinc-300 text-sm italic">"{prediction.raw_transcript}"</p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <div>
          <p className="text-xs text-zinc-400">Asset</p>
          <p className="text-white font-medium">{prediction.asset}</p>
        </div>
        <div>
          <p className="text-xs text-zinc-400">Direction</p>
          <p className="text-white font-medium capitalize">{prediction.direction}</p>
        </div>
        <div>
          <p className="text-xs text-zinc-400">Entry Price</p>
          <p className="text-white font-medium">{formatPrice(prediction.entry_price)}</p>
        </div>
        {prediction.target_price != null && (
          <div>
            <p className="text-xs text-zinc-400">Target Price</p>
            <p className="text-white font-medium">{formatPrice(prediction.target_price)}</p>
          </div>
        )}
        {prediction.timeframe && (
          <div>
            <p className="text-xs text-zinc-400">Timeframe</p>
            <p className="text-white font-medium">{prediction.timeframe}</p>
          </div>
        )}
        {currentPrice != null && (
          <div>
            <p className="text-xs text-zinc-400">Current Price</p>
            <p className="text-white font-medium">{formatPrice(currentPrice)}</p>
          </div>
        )}
        {prediction.note && (
          <div className="col-span-full">
            <p className="text-xs text-zinc-400">Note</p>
            <p className="text-white">{prediction.note}</p>
          </div>
        )}
      </div>

      <div>
        <h3 className="text-sm font-medium text-zinc-300 mb-2">Check-in Timeline</h3>
        <CheckinTimeline checkins={prediction.checkins} entryPrice={prediction.entry_price} />
      </div>

      <div className="flex items-center gap-3 text-xs text-zinc-500">
        <span>Created {format(new Date(prediction.created_at), 'MMM d, yyyy HH:mm')}</span>
        {prediction.audio_path && (
          <a
            href={`/api/${prediction.audio_path}`}
            className="text-blue-400 hover:text-blue-300 underline"
          >
            Play recording
          </a>
        )}
        <button
          onClick={onNavigateJournal}
          className="text-blue-400 hover:text-blue-300 underline"
        >
          View Journal
        </button>
      </div>
    </div>
  )
}