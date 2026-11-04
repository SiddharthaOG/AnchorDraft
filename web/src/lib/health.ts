/** Health check API client. */

export interface HealthResponse {
  status: string
  version: string
  time: string
}

export class HealthError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly originalError?: Error,
  ) {
    super(message)
    this.name = 'HealthError'
  }
}

function getEngineUrl(): string {
  return import.meta.env.VITE_ENGINE_URL || 'http://localhost:8000'
}

export async function fetchHealth(): Promise<HealthResponse> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 10000)

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
      throw new HealthError('Health check timeout', 504, err)
    }
    throw new HealthError(
      err instanceof Error ? err.message : 'Network error',
      0,
      err instanceof Error ? err : undefined,
    )
  } finally {
    clearTimeout(timeoutId)
  }
}