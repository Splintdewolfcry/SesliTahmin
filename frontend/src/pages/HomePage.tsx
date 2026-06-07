import { useState, useEffect, useCallback } from 'react'
import { listPredictions, getPrices, refreshAllPredictions } from '../hooks/usePredictions'
import type { Prediction, PriceQuote } from '../types'
import PredictionCard from '../components/PredictionCard'
import { RecordingFlow } from '../components/AudioRecorder'
import LoadingSpinner from '../components/LoadingSpinner'

function AuthDialog({ onAuth }: { onAuth: (token: string) => void }) {
  const [token, setToken] = useState('')
  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
      <div className="bg-zinc-800 border border-zinc-600 rounded-lg p-6 max-w-sm w-full mx-4">
        <h2 className="text-white font-bold text-lg mb-2">Authentication Required</h2>
        <p className="text-zinc-400 text-sm mb-4">Enter your auth token to continue.</p>
        <input
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && token.trim() && onAuth(token.trim())}
          placeholder="Auth token"
          className="w-full bg-zinc-700 text-white rounded px-3 py-2 text-sm border border-zinc-600 focus:border-blue-500 focus:outline-none mb-3"
          autoFocus
        />
        <button
          onClick={() => token.trim() && onAuth(token.trim())}
          disabled={!token.trim()}
          className="w-full px-4 py-2 bg-blue-600 rounded text-sm font-medium hover:bg-blue-500 disabled:opacity-50 transition-colors"
        >
          Connect
        </button>
      </div>
    </div>
  )
}

export default function HomePage() {
  const [authed, setAuthed] = useState(() => !!localStorage.getItem('auth_token'))
  const [predictions, setPredictions] = useState<Prediction[]>([])
  const [prices, setPrices] = useState<Record<string, PriceQuote>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [showRecorder, setShowRecorder] = useState(false)

  const fetchData = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const [preds, p] = await Promise.all([listPredictions(), getPrices()])
      setPredictions(preds)
      setPrices(p)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load predictions')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (authed) fetchData()
  }, [authed, fetchData])

  const handleAuth = (token: string) => {
    localStorage.setItem('auth_token', token)
    setAuthed(true)
  }

  const handleRefreshAll = async () => {
    try {
      setRefreshing(true)
      await refreshAllPredictions()
      await fetchData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Refresh failed')
    } finally {
      setRefreshing(false)
    }
  }

  const handlePredictionCreated = (_p: Prediction) => {
    fetchData()
    setShowRecorder(false)
  }

  if (!authed) return <AuthDialog onAuth={handleAuth} />

  return (
    <div className="min-h-screen bg-zinc-900 text-white">
      <div className="max-w-2xl mx-auto px-4 py-6">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold">SesliTahmin</h1>
          <div className="flex gap-2">
            <button
              onClick={handleRefreshAll}
              disabled={refreshing}
              className="px-3 py-1.5 bg-zinc-700 rounded text-sm hover:bg-zinc-600 transition-colors disabled:opacity-50"
            >
              {refreshing ? 'Refreshing...' : 'Refresh All'}
            </button>
            <button
              onClick={() => setShowRecorder(!showRecorder)}
              className="px-3 py-1.5 bg-blue-600 rounded text-sm font-medium hover:bg-blue-500 transition-colors"
            >
              {showRecorder ? 'Cancel' : 'Record Prediction'}
            </button>
          </div>
        </div>

        {error && (
          <div className="bg-red-900/30 border border-red-700 rounded text-red-400 p-3 mb-4 text-sm">
            {error}
            <button onClick={() => setError(null)} className="ml-2 underline">
              Dismiss
            </button>
          </div>
        )}

        {showRecorder && (
          <div className="bg-zinc-800 border border-zinc-700 rounded-lg p-4 mb-4">
            <RecordingFlow onPredictionCreated={handlePredictionCreated} />
          </div>
        )}

        {loading ? (
          <LoadingSpinner text="Loading predictions..." />
        ) : predictions.length === 0 ? (
          <div className="text-center py-16">
            <p className="text-zinc-500 text-lg mb-2">No predictions yet</p>
            <p className="text-zinc-600 text-sm">Record your first prediction to get started.</p>
            <button
              onClick={() => setShowRecorder(true)}
              className="mt-4 px-4 py-2 bg-blue-600 rounded text-sm font-medium hover:bg-blue-500 transition-colors"
            >
              Record Prediction
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {predictions.map((p) => (
              <PredictionCard key={p.id} prediction={p} prices={prices} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}