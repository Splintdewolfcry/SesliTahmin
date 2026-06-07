import { useState, useEffect, useCallback } from 'react'
import { useAudioRecorder } from '../hooks/useAudioRecorder'
import { transcribeAudio, createPrediction } from '../hooks/usePredictions'
import type { Prediction } from '../types'
import LoadingSpinner from './LoadingSpinner'

interface AudioRecorderProps {
  onRecordingComplete: (blob: Blob, duration: number) => void
}

function MicButton({ onRecordingComplete }: AudioRecorderProps) {
  const { startRecording, stopRecording, isRecording, error, duration, audioBlob } =
    useAudioRecorder()
  const [phase, setPhase] = useState<'idle' | 'recording' | 'transcribing'>('idle')

  useEffect(() => {
    if (audioBlob && phase === 'recording') {
      setPhase('transcribing')
    }
  }, [audioBlob, phase])

  const handleClick = useCallback(() => {
    if (phase === 'transcribing') return
    if (isRecording) {
      stopRecording()
    } else {
      setPhase('recording')
      startRecording()
    }
  }, [isRecording, phase, startRecording, stopRecording])

  useEffect(() => {
    if (audioBlob && phase === 'transcribing') {
      onRecordingComplete(audioBlob, duration)
      setPhase('idle')
    }
  }, [audioBlob, phase, duration, onRecordingComplete])

  if (error) {
    return (
      <div className="text-center">
        <p className="text-red-400 text-sm mb-2">{error}</p>
        <a
          href="https://support.google.com/chrome/answer/2693767"
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-400 text-xs underline"
        >
          Open browser microphone settings
        </a>
      </div>
    )
  }

  if (phase === 'transcribing') {
    return <LoadingSpinner text="Processing recording..." />
  }

  return (
    <div className="flex flex-col items-center gap-2">
      <button
        onClick={handleClick}
        className={`w-16 h-16 rounded-full flex items-center justify-center text-2xl transition-all duration-200 ${
          isRecording
            ? 'bg-red-600 shadow-lg shadow-red-600/50 animate-pulse'
            : 'bg-zinc-700 hover:bg-zinc-600'
        }`}
        aria-label={isRecording ? 'Stop recording' : 'Start recording'}
      >
        🎙️
      </button>
      {isRecording && (
        <span className="text-red-400 text-sm font-mono">
          {Math.floor(duration / 60)}:{(duration % 60).toString().padStart(2, '0')}
        </span>
      )}
    </div>
  )
}

function RecordingFlow({ onPredictionCreated }: { onPredictionCreated: (p: Prediction) => void }) {
  const [phase, setPhase] = useState<
    'record' | 'transcribing' | 'creating' | 'done' | 'error'
  >('record')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const handleRecordingComplete = useCallback(
    async (blob: Blob, _duration: number) => {
      setPhase('transcribing')
      try {
        const file = new File([blob], 'recording.webm', { type: blob.type || 'audio/webm' })
        const asr = await transcribeAudio(file)
        setPhase('creating')
        const prediction = await createPrediction({
          transcript: asr.transcript,
          language: asr.language || 'en',
          voice_started_at: new Date().toISOString(),
        })
        onPredictionCreated(prediction)
        setPhase('done')
      } catch (err) {
        setErrorMsg(err instanceof Error ? err.message : 'Unknown error')
        setPhase('error')
      }
    },
    [onPredictionCreated],
  )

  if (phase === 'done') {
    return (
      <div className="text-center">
        <p className="text-green-400 mb-2">Prediction created!</p>
        <button
          onClick={() => {
            setPhase('record')
            setErrorMsg(null)
          }}
          className="px-4 py-2 bg-zinc-700 rounded hover:bg-zinc-600 text-sm"
        >
          Record another
        </button>
      </div>
    )
  }

  if (phase === 'transcribing') {
    return <LoadingSpinner text="Transcribing with Whisper..." />
  }

  if (phase === 'creating') {
    return <LoadingSpinner text="Extracting prediction..." />
  }

  if (phase === 'error') {
    return (
      <div className="text-center">
        <p className="text-red-400 text-sm mb-2">{errorMsg}</p>
        <button
          onClick={() => {
            setPhase('record')
            setErrorMsg(null)
          }}
          className="px-4 py-2 bg-zinc-700 rounded hover:bg-zinc-600 text-sm"
        >
          Try again
        </button>
      </div>
    )
  }

  return <MicButton onRecordingComplete={handleRecordingComplete} />
}

export { RecordingFlow }
export default MicButton