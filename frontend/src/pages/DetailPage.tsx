import { useParams } from 'react-router-dom'

export default function DetailPage() {
  const { id } = useParams<{ id: string }>()

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <h1 className="text-3xl font-bold text-gray-800">
        Prediction Detail - {id}
      </h1>
    </div>
  )
}