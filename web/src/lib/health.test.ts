import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fetchHealth, HealthError, HealthResponse } from './health'

const mockFetch = vi.fn()
global.fetch = mockFetch

describe('fetchHealth', () => {
  beforeEach(() => {
    mockFetch.mockReset()
    vi.stubEnv('VITE_ENGINE_URL', 'http://test-engine:8000')
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('returns health response on success', async () => {
    const mockResponse: HealthResponse = {
      status: 'ok',
      version: '1.2.3',
      time: '2026-11-04T12:00:00.000Z',
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockResponse,
    })

    const result = await fetchHealth()

    expect(result).toEqual(mockResponse)
    expect(mockFetch).toHaveBeenCalledOnce()
    const call = mockFetch.mock.calls[0]
    expect(call[0]).toBe('http://test-engine:8000/v1/health')
    expect(call[1]).toMatchObject({
      headers: expect.objectContaining({
        'X-Request-Id': expect.any(String),
      }),
    })
  })

  it('throws HealthError on HTTP error status', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 503,
      statusText: 'Service Unavailable',
    })

    const promise = fetchHealth()
    await expect(promise).rejects.toThrow(HealthError)
    await expect(promise).rejects.toMatchObject({
      status: 503,
      message: 'Health check failed: 503 Service Unavailable',
    })
  })

  it('throws HealthError on network error', async () => {
    const networkError = new TypeError('Failed to fetch')
    mockFetch.mockRejectedValueOnce(networkError)

    const promise = fetchHealth()
    await expect(promise).rejects.toThrow(HealthError)
    await expect(promise).rejects.toMatchObject({
      status: 0,
      message: 'Failed to fetch',
      originalError: networkError,
    })
  })

  it('throws HealthError on timeout', async () => {
    const abortError = new DOMException('Aborted', 'AbortError')
    mockFetch.mockRejectedValueOnce(abortError)

    const promise = fetchHealth()
    await expect(promise).rejects.toThrow(HealthError)
    await expect(promise).rejects.toMatchObject({
      status: 504,
      message: 'Health check timeout',
    })
  })

  it('throws HealthError on invalid response shape', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: 'not-ok' }), // missing version, time
    })

    const promise = fetchHealth()
    await expect(promise).rejects.toThrow(HealthError)
    await expect(promise).rejects.toMatchObject({
      status: 500,
      message: 'Invalid health response shape',
    })
  })

  it('includes X-Request-Id header', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        status: 'ok',
        version: '1.0.0',
        time: '2026-11-04T12:00:00.000Z',
      }),
    })

    await fetchHealth()

    const call = mockFetch.mock.calls[0]
    const headers = call[1]?.headers as Record<string, string>
    expect(headers['X-Request-Id']).toBeDefined()
    // Should be a valid UUID format
    expect(headers['X-Request-Id']).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    )
  })
})