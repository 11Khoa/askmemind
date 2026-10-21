import { session } from './session'
import type { TokenResponse } from './types'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function checkResponse(response: Response) {
  if (response.ok) return response
  let message = `Request failed with status ${response.status}`
  try {
    const payload = (await response.json()) as { detail?: unknown }
    if (typeof payload.detail === 'string') message = payload.detail
    else if (payload.detail) message = JSON.stringify(payload.detail)
  } catch {
    // Preserve the HTTP fallback for non-JSON error responses.
  }
  throw new ApiError(message, response.status)
}

function fetchResponse(path: string, options: RequestInit, accessToken?: string) {
  const headers = new Headers(options.headers)
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  if (options.body && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  return fetch(`${API_BASE_URL}${path}`, { ...options, headers })
}

let refreshing: { tokens: TokenResponse; promise: Promise<void> } | null = null

async function refreshTokens(tokens: TokenResponse) {
  if (session.get() !== tokens) return
  // Rotation is single-use: concurrent 401s must share the same refresh request.
  if (refreshing?.tokens === tokens) return refreshing.promise

  const promise = (async () => {
    try {
      const response = await checkResponse(await fetchResponse('/auth/refresh', {
        method: 'POST',
        body: JSON.stringify({ refresh_token: tokens.refresh_token }),
      }))
      const next = await response.json() as TokenResponse
      if (session.get() === tokens) session.rotate(next)
    } catch (error) {
      // A lost response may have consumed the token; never replay it.
      if (session.get() === tokens) session.set(null)
      throw error
    } finally {
      if (refreshing?.tokens === tokens) refreshing = null
    }
  })()
  refreshing = { tokens, promise }
  return promise
}

type RequestOptions = RequestInit | (() => RequestInit)

export async function authenticatedResponse(path: string, options: RequestOptions = {}) {
  const original = session.get()
  const version = session.version()
  if (!original) throw new ApiError('Please sign in again', 401)
  const init = () => typeof options === 'function' ? options() : options
  let response = await fetchResponse(path, init(), original.access_token)
  if (response.status === 401) {
    await response.body?.cancel()
    await refreshTokens(original)
    const current = session.get()
    // Do not retry an old request under a different signed-in account.
    if (!current || session.version() !== version) {
      throw new ApiError('Please sign in again', 401)
    }
    if (init().signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    response = await fetchResponse(path, init(), current.access_token)
    if (response.status === 401 && session.get() === current) session.set(null)
  }
  return checkResponse(response)
}

export async function request<T>(
  path: string,
  options: RequestOptions = {},
  authenticated = false,
): Promise<T> {
  const response = authenticated
    ? await authenticatedResponse(path, options)
    : await checkResponse(await fetchResponse(path, typeof options === 'function' ? options() : options))
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
