import type {
  Prediction,
  CreatePredictionRequest,
  PatchPredictionRequest,
  PriceQuote,
  AsrResult,
} from '../types'

function getToken(): string | null {
  return localStorage.getItem('auth_token')
}

function authHeaders(): HeadersInit {
  const token = getToken()
  const headers: HeadersInit = {}
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (res.status === 401) {
    localStorage.removeItem('auth_token')
    throw new Error('Unauthorized — please re-enter your auth token.')
  }
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API error ${res.status}: ${body}`)
  }
  return res.json()
}

async function handleVoid(res: Response): Promise<void> {
  if (res.status === 401) {
    localStorage.removeItem('auth_token')
    throw new Error('Unauthorized — please re-enter your auth token.')
  }
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API error ${res.status}: ${body}`)
  }
}

export async function listPredictions(): Promise<Prediction[]> {
  const res = await fetch('/api/predictions/', {
    headers: authHeaders(),
  })
  return handleResponse<Prediction[]>(res)
}

export async function getPrediction(id: string): Promise<Prediction> {
  const res = await fetch(`/api/predictions/${id}`, {
    headers: authHeaders(),
  })
  return handleResponse<Prediction>(res)
}

export async function createPrediction(
  req: CreatePredictionRequest,
): Promise<Prediction> {
  const res = await fetch('/api/predictions/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(req),
  })
  return handleResponse<Prediction>(res)
}

export async function patchPrediction(
  id: string,
  req: PatchPredictionRequest,
): Promise<Prediction> {
  const res = await fetch(`/api/predictions/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(req),
  })
  return handleResponse<Prediction>(res)
}

export async function deletePrediction(id: string): Promise<void> {
  const res = await fetch(`/api/predictions/${id}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  return handleVoid(res)
}

export async function refreshPrediction(id: string): Promise<Prediction> {
  const res = await fetch(`/api/predictions/${id}/refresh`, {
    method: 'POST',
    headers: authHeaders(),
  })
  return handleResponse<Prediction>(res)
}

export async function refreshAllPredictions(): Promise<{
  refreshed: number
  errors: Array<{ id: string; error: string }>
}> {
  const res = await fetch('/api/predictions/refresh-all', {
    method: 'POST',
    headers: authHeaders(),
  })
  return handleResponse<{
    refreshed: number
    errors: Array<{ id: string; error: string }>
  }>(res)
}

export async function getJournal(id: string): Promise<string> {
  const res = await fetch(`/api/predictions/${id}/journal.md`, {
    headers: authHeaders(),
  })
  if (res.status === 401) {
    localStorage.removeItem('auth_token')
    throw new Error('Unauthorized — please re-enter your auth token.')
  }
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API error ${res.status}: ${body}`)
  }
  return res.text()
}

export async function getPrices(): Promise<Record<string, PriceQuote>> {
  const res = await fetch('/api/prices/', {
    headers: authHeaders(),
  })
  return handleResponse<Record<string, PriceQuote>>(res)
}

export async function transcribeAudio(file: File): Promise<AsrResult> {
  const form = new FormData()
  form.append('file', file, file.name)
  const res = await fetch('/api/predictions/transcribe', {
    method: 'POST',
    headers: authHeaders(),
    body: form,
  })
  return handleResponse<AsrResult>(res)
}