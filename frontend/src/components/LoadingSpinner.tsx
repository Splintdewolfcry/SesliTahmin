interface LoadingSpinnerProps {
  text?: string
}

export default function LoadingSpinner({ text }: LoadingSpinnerProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-8">
      <div className="w-8 h-8 border-2 border-zinc-500 border-t-blue-500 rounded-full animate-spin" />
      {text && <p className="text-zinc-400 text-sm">{text}</p>}
    </div>
  )
}