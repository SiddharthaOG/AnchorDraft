import { useEffect, useState } from 'react'

interface HealthResponse {
  status: string
  version: string
  time: string
}

interface HealthState {
  data: HealthResponse | null
  error: string | null
  loading: boolean
}

const ENGINE_URL = import.meta.env.VITE_ENGINE_URL || 'http://localhost:8000'

export function HealthCheck() {
  const [state, setState] = useState<HealthState>({
    data: null,
    error: null,
    loading: true,
  })

  useEffect(() => {
    let mounted = true

    async function fetchHealth() {
      try {
        const response = await fetch(`${ENGINE_URL}/v1/health`, {
          headers: {
            'X-Request-Id': crypto.randomUUID(),
          },
        })

        if (!mounted) return

        if (!response.ok) {
          setState({
            data: null,
            error: `Health check failed: ${response.status} ${response.statusText}`,
            loading: false,
          })
          return
        }

        const data = (await response.json()) as HealthResponse
        setState({ data, error: null, loading: false })
      } catch (err) {
        if (!mounted) return
        setState({
          data: null,
          error: err instanceof Error ? err.message : 'Unknown error',
          loading: false,
        })
      }
    }

    fetchHealth()

    return () => {
      mounted = false
    }
  }, [])

  if (state.loading) {
    return (
      <div className="bg-white rounded-lg shadow p-6 text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto mb-4"></div>
        <p className="text-gray-600">Checking engine health...</p>
      </div>
    )
  }

  if (state.error) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <h2 className="text-red-800 font-semibold mb-2">Health Check Failed</h2>
          <p className="text-red-700">{state.error}</p>
          <p className="text-red-600 text-sm mt-2">
            Engine URL: {ENGINE_URL}/v1/health
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-4">
        <h2 className="text-green-800 font-semibold mb-2">Engine Healthy</h2>
        <div className="space-y-2 text-green-700 text-sm">
          <p><strong>Status:</strong> {state.data?.status}</p>
          <p><strong>Version:</strong> {state.data?.version}</p>
          <p><strong>Time:</strong> {state.data?.time}</p>
        </div>
      </div>
      <details className="text-sm text-gray-500">
        <summary className="cursor-pointer mb-2">Request Details</summary>
        <pre className="bg-gray-100 p-3 rounded overflow-auto">
          {JSON.stringify(state.data, null, 2)}
        </pre>
      </details>
    </div>
  )
}