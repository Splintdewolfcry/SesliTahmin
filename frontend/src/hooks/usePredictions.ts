import type { Prediction } from '../types'

export function usePredictions() {
  return { predictions: [] as Prediction[], loading: false, error: null as string | null }
}