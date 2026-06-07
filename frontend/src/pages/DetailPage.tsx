import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  getPrediction,
  getPrices,
  refreshPrediction as refreshPredictionApi,
  patchPrediction,
  deletePrediction as deletePredictionApi,
  getJournal,
} from '../hooks/usePredictions'
import type { Prediction, PriceQuote, PatchPredictionRequest } from '../types'
import PredictionDetail from '../components/PredictionDetail'
import LoadingSpinner from '../components/LoadingSpinner'

export default function DetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [prediction, setPrediction] = useState<Prediction | null>(null)
  const [prices, setPrices] = useState<Record<string, PriceQuote>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [journal, setJournal] = useState<string | null>(null)
  const [showJournal, setShowJournal] = useState(false)

  const fetchData = useCallback(async () => {
    if (!id) return
    try {
      setLoading(true)
      setError(null)
      const [p, pr] = await Promise.all([getPrediction(id), getPrices()])
      setPrediction(p)
      setPrices(pr)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load prediction')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const handleRefresh = async () => {
    if (!id) return
    const updated = await refreshPredictionApi(id)
    setPrediction(updated)
  }

  const handleEdit = async (patch: PatchPredictionRequest) => {
    if (!id) return
    const updated = await patchPrediction(id, patch)
    setPrediction(updated)
  }

  const handleDelete = async () => {
    if (!id) return
    await deletePredictionApi(id)
    navigate('/')
  }

  const handleNavigateJournal = async () => {
    if (!id) return
    if (!journal) {
      const md = await getJournal(id)
      setJournal(md)
    }
    setShowJournal(!showJournal)
  }

  if (loading) return <LoadingSpinner text="Loading prediction..." />
  if (error) {
    return (
      <div className="min-h-screen bg-zinc-900 text-white flex flex-col items-center justify-center">
        <p className="text-red-400 mb-4">{error}</p>
        <div className="flex gap-2">
          <button onClick={fetchData} className="px-4 py-2 bg-zinc-700 rounded text-sm hover:bg-zinc-600">
            Retry
          </button>
          <button onClick={() => navigate('/')} className="px-4 py-2 bg-zinc-700 rounded text-sm hover:bg-zinc-600">
            Home
          </button>
        </div>
      </div>
    )
  }
  if (!prediction) return null

  return (
    <div className="min-h-screen bg-zinc-900 text-white">
      <div className="max-w-2xl mx-auto px-4 py-6">
        <a href="/" className="text-blue-400 text-sm hover:text-blue-300 mb-4 inline-block">
          &larr; Back to list
        </a>

        <PredictionDetail
          prediction={prediction}
          prices={prices}
          onRefresh={handleRefresh}
          onEdit={handleEdit}
          onDelete={handleDelete}
          onNavigateJournal={handleNavigateJournal}
        />

        {showJournal && journal && (
          <div className="mt-4 bg-zinc-800 border border-zinc-700 rounded-lg p-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium text-zinc-300">Journal</h3>
              <button
                onClick={() => setShowJournal(false)}
                className="text-xs text-zinc-500 hover:text-zinc-400"
              >
                Close
              </button>
            </div>
            <pre className="text-xs text-zinc-300 whitespace-pre-wrap font-mono">{journal}</pre>
          </div>
        )}
      </div>
    </div>
  )
}