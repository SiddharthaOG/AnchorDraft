/** Health check API client. */

export interface HealthResponse {
  status: string
  version: string
  time: string
}

export interface HealthStatus {
  data: HealthResponse | null
  error: string | null
  loading: boolean
  wakingUp: boolean
}

export class HealthError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly originalError?: Error,
    public readonly isTimeout: boolean = false,
  ) {
    super(message)
    this.name = 'HealthError'
  }
}

function getEngineUrl(): string {
  return import.meta.env.VITE_ENGINE_URL || 'http://localhost:8000'
}

export async function fetchHealth(
  onWakingUp?: () => void,
): Promise<HealthResponse> {
  const controller = new AbortController()
  // 60s timeout for free-tier cold starts
  const timeoutId = setTimeout(() => controller.abort(), 60000)
  // 3s warning for "waking up" state
  const warningId = setTimeout(() => {
    onWakingUp?.()
  }, 3000)

  try {
    const response = await fetch(`${getEngineUrl()}/v1/health`, {
      signal: controller.signal,
      headers: {
        'X-Request-Id': crypto.randomUUID(),
      },
    })

    if (!response.ok) {
      throw new HealthError(
        `Health check failed: ${response.status} ${response.statusText}`,
        response.status,
      )
    }

    const data = (await response.json()) as HealthResponse

    if (data.status !== 'ok' || !data.version || !data.time) {
      throw new HealthError('Invalid health response shape', 500)
    }

    return data
  } catch (err) {
    if (err instanceof HealthError) throw err
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new HealthError('Health check timeout after 60s', 504, err, true)
    }
    throw new HealthError(
      err instanceof Error ? err.message : 'Network error',
      0,
      err instanceof Error ? err : undefined,
    )
  } finally {
    clearTimeout(timeoutId)
    clearTimeout(warningId)
  }
}