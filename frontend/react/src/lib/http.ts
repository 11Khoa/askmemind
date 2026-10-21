import { session } from './session'
import type { TokenResponse } from './types'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'
const COOKIE_AUTH_PATHS = new Set(['/auth/login', '/auth/refresh', '/auth/logout'])

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
  if (COOKIE_AUTH_PATHS.has(path)) headers.set('X-CSRF-Protection', '1')
  return fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
    credentials: 'include',
    ...(COOKIE_AUTH_PATHS.has(path) ? { cache: 'no-store' as const } : {}),
  })
}

async function readAccessToken(response: Response): Promise<TokenResponse> {
  const data = await response.json() as Partial<TokenResponse>
  if (!data.access_token || typeof data.access_token !== 'string') {
    throw new ApiError('Authentication response did not include an access token', 502)
  }
  // Only access tokens enter application state, even if an old API sends extra fields.
  return { access_token: data.access_token, token_type: data.token_type || 'bearer' }
}

function withSessionLock<T>(work: () => Promise<T>) {
  return typeof navigator !== 'undefined' && navigator.locks
    ? navigator.locks.request('askmemind:auth-session', work)
    : work()
}

let refreshing: { version: number; promise: Promise<void> } | null = null

async function refreshTokens(original: TokenResponse | null) {
  const version = session.version()
  if (session.get() !== original) return
  if (refreshing?.version === version) return refreshing.promise

  const promise = withSessionLock(async () => {
    if (session.version() !== version || session.get() !== original) return
    try {
      const response = await checkResponse(await fetchResponse('/auth/refresh', { method: 'POST' }))
      const next = await readAccessToken(response)
      if (!session.finishRefresh(version, next)) throw new ApiError('Please sign in again', 401)
    } catch (error) {
      session.failRefresh(version)
      throw error
    } finally {
      if (refreshing?.version === version) refreshing = null
    }
  })
  refreshing = { version, promise }
  return promise
}

export function loginSession(email: string, password: string) {
  return withSessionLock(async () => {
    const response = await checkResponse(await fetchResponse('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }))
    return readAccessToken(response)
  })
}

export async function restoreSession() {
  if (session.status() === 'restoring') await refreshTokens(session.get())
}

export async function logoutSession() {
  await restoreSession()
  const version = session.version()
  try {
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const current = session.get()
      if (!current || session.version() !== version) throw new ApiError('Please sign in again', 401)
      const response = await withSessionLock(async () => {
        if (session.version() !== version) throw new ApiError('Please sign in again', 401)
        const result = await fetchResponse('/auth/logout', { method: 'POST' }, current.access_token)
        if (result.status !== 401 || attempt === 1) {
          try {
            return await checkResponse(result)
          } finally {
            if (session.version() === version) session.set(null)
          }
        }
        return result
      })
      if (response.ok) return
      await response.body?.cancel()
      await refreshTokens(current)
    }
  } finally {
    if (session.version() === version) session.set(null)
  }
}

export async function authenticatedResponse(path: string, options: RequestInit = {}) {
  await restoreSession()
  const original = session.get()
  const version = session.version()
  if (!original) throw new ApiError('Please sign in again', 401)
  let response = await fetchResponse(path, options, original.access_token)
  if (response.status === 401) {
    await response.body?.cancel()
    await refreshTokens(original)
    const current = session.get()
    if (!current || session.version() !== version) throw new ApiError('Please sign in again', 401)
    if (options.signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    response = await fetchResponse(path, options, current.access_token)
    if (response.status === 401) session.failRefresh(version)
  }
  return checkResponse(response)
}

export async function request<T>(
  path: string,
  options: RequestInit = {},
  authenticated = false,
): Promise<T> {
  const response = authenticated
    ? await authenticatedResponse(path, options)
    : await checkResponse(await fetchResponse(path, options))
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
