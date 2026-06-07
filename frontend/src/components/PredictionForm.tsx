import { useState } from 'react'
import type { Prediction, Asset, Direction, PatchPredictionRequest } from '../types'

interface PredictionFormProps {
  prediction: Prediction
  onSave: (patch: PatchPredictionRequest) => void
  onCancel: () => void
}

const ASSETS: Asset[] = ['BTC', 'ETH', 'SOL', 'BNB']
const DIRECTIONS: Direction[] = ['up', 'down', 'neutral']
const TIMEFRAMES = ['15min', '45min', '1h', '6h', '12h', '1d', '3d', '1w']

export default function PredictionForm({ prediction, onSave, onCancel }: PredictionFormProps) {
  const [asset, setAsset] = useState<Asset>(prediction.asset)
  const [direction, setDirection] = useState<Direction>(prediction.direction)
  const [targetPrice, setTargetPrice] = useState<string>(
    prediction.target_price != null ? String(prediction.target_price) : '',
  )
  const [timeframe, setTimeframe] = useState<string>(prediction.timeframe || '')
  const [note, setNote] = useState<string>(prediction.note || '')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const patch: PatchPredictionRequest = {}
    if (asset !== prediction.asset) patch.asset = asset
    if (direction !== prediction.direction) patch.direction = direction
    if (targetPrice !== (prediction.target_price != null ? String(prediction.target_price) : ''))
      patch.target_price = targetPrice ? parseFloat(targetPrice) : null
    if (timeframe !== (prediction.timeframe || '')) patch.timeframe = timeframe || null
    if (note !== (prediction.note || '')) patch.note = note || null
    onSave(patch)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="bg-zinc-800/60 rounded-lg p-3 mb-4">
        <p className="text-xs text-zinc-400 mb-1">Transcript</p>
        <p className="text-zinc-300 text-sm italic">"{prediction.raw_transcript}"</p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-zinc-400 mb-1">Asset</label>
          <select
            value={asset}
            onChange={(e) => setAsset(e.target.value as Asset)}
            className="w-full bg-zinc-700 text-white rounded px-3 py-2 text-sm border border-zinc-600 focus:border-blue-500 focus:outline-none"
          >
            {ASSETS.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs text-zinc-400 mb-1">Direction</label>
          <select
            value={direction}
            onChange={(e) => setDirection(e.target.value as Direction)}
            className="w-full bg-zinc-700 text-white rounded px-3 py-2 text-sm border border-zinc-600 focus:border-blue-500 focus:outline-none"
          >
            {DIRECTIONS.map((d) => (
              <option key={d} value={d}>
                {d === 'up' ? '↑ Up' : d === 'down' ? '↓ Down' : '→ Neutral'}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs text-zinc-400 mb-1">Target Price</label>
          <input
            type="number"
            step="any"
            value={targetPrice}
            onChange={(e) => setTargetPrice(e.target.value)}
            placeholder="Optional"
            className="w-full bg-zinc-700 text-white rounded px-3 py-2 text-sm border border-zinc-600 focus:border-blue-500 focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-xs text-zinc-400 mb-1">Timeframe</label>
          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            className="w-full bg-zinc-700 text-white rounded px-3 py-2 text-sm border border-zinc-600 focus:border-blue-500 focus:outline-none"
          >
            <option value="">None</option>
            {TIMEFRAMES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <label className="block text-xs text-zinc-400 mb-1">Note</label>
        <input
          type="text"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Optional note"
          className="w-full bg-zinc-700 text-white rounded px-3 py-2 text-sm border border-zinc-600 focus:border-blue-500 focus:outline-none"
        />
      </div>

      <div className="flex gap-2 pt-2">
        <button
          type="submit"
          className="flex-1 px-4 py-2 bg-blue-600 rounded text-sm font-medium hover:bg-blue-500 transition-colors"
        >
          Save
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="flex-1 px-4 py-2 bg-zinc-700 rounded text-sm hover:bg-zinc-600 transition-colors"
        >
          Cancel
        </button>
      </div>
    </form>
  )
}