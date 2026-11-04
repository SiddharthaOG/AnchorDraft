import { useEffect, useState, useCallback } from 'react'
import { fetchHealth, HealthError, HealthStatus } from '../../lib/health'

export function HealthCheck() {
  const [state, setState] = useState<HealthStatus>({
    data: null,
    error: null,
    loading: true,
    wakingUp: false,
  })

  const handleWakingUp = useCallback(() => {
    setState(prev => ({ ...prev, wakingUp: true }))
  }, [])

  useEffect(() => {
    let mounted = true

    async function loadHealth() {
      try {
        const data = await fetchHealth(handleWakingUp)
        if (!mounted) return
        setState({ data, error: null, loading: false, wakingUp: false })
      } catch (err: unknown) {
        if (!mounted) return
        const message = err instanceof HealthError
          ? `${err.message}${err.status ? ` (${err.status})` : ''}`
          : err instanceof Error
            ? err.message
            : 'Unknown error'
        setState({ data: null, error: message, loading: false, wakingUp: false })
      }
    }

    loadHealth()

    return () => {
      mounted = false
    }
  }, [handleWakingUp])

  if (state.loading && !state.wakingUp) {
    return (
      <div className="bg-white rounded-lg shadow p-6 text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto mb-4"></div>
        <p className="text-gray-600">Checking engine health...</p>
      </div>
    )
  }

  if (state.wakingUp) {
    return (
      <div className="bg-white rounded-lg shadow p-6 text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto mb-4"></div>
        <p className="text-yellow-700">Engine is waking up… (free tier cold start)</p>
        <p className="text-gray-500 text-sm mt-1">This may take up to 60 seconds</p>
      </div>
    )
  }

  if (state.error) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <h2 className="text-red-800 font-semibold mb-2">Health Check Failed</h2>
          <p className="text-red-700">{state.error}</p>
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