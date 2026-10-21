import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '../src/lib/api'
import { session } from '../src/lib/session'

const original = { access_token: 'old-access', refresh_token: 'old-refresh', token_type: 'bearer' }
const rotated = { access_token: 'new-access', refresh_token: 'new-refresh', token_type: 'bearer' }
const json = (data: unknown, status = 200) => Response.json(data, { status })
const unauthorized = () => json({ detail: 'Token expired' }, 401)
const fetchMock = vi.fn<typeof fetch>()
const refreshCalls = () => fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/auth/refresh'))

beforeEach(() => {
  session.set({ ...original })
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => {
  session.set(null)
  fetchMock.mockReset()
  vi.unstubAllGlobals()
})

it('shares one refresh across concurrent 401s and uses the new pair afterward', async () => {
  const refresh = Promise.withResolvers<Response>()
  fetchMock.mockImplementation(async (url, init) => {
    if (String(url).endsWith('/auth/refresh')) return refresh.promise
    return new Headers(init?.headers).get('Authorization') === 'Bearer new-access' ? json([]) : unauthorized()
  })
  const requests = Promise.all([api.me(), api.listChats(), api.listDocuments()])
  await vi.waitFor(() => expect(refreshCalls()).toHaveLength(1))
  refresh.resolve(json(rotated))
  await requests
  expect(session.get()).toEqual(rotated)
  expect(fetchMock).toHaveBeenCalledTimes(7)
  await api.listChats()
  expect(new Headers(fetchMock.mock.calls.at(-1)?.[1]?.headers).get('Authorization')).toBe('Bearer new-access')
})

it('does not replay an old refresh token after a late 401 response', async () => {
  const late = Promise.withResolvers<Response>()
  fetchMock.mockResolvedValueOnce(late.promise).mockResolvedValueOnce(unauthorized())
    .mockResolvedValueOnce(json(rotated)).mockResolvedValueOnce(json([])).mockResolvedValueOnce(json([]))
  const slow = api.listChats()
  await api.listDocuments()
  late.resolve(unauthorized())
  await slow
  expect(refreshCalls()).toHaveLength(1)
})

it.each(['invalid', 'network'])('discards a refresh token after %s failure and never replays it', async (failure) => {
  fetchMock.mockResolvedValueOnce(unauthorized())
  if (failure === 'invalid') fetchMock.mockResolvedValueOnce(unauthorized())
  else fetchMock.mockRejectedValueOnce(new TypeError('Network failure'))
  await expect(api.me()).rejects.toThrow()
  expect(session.get()).toBeNull()
  await expect(api.me()).rejects.toMatchObject({ status: 401 })
  expect(fetchMock).toHaveBeenCalledTimes(2)
})

it('stops after one retry if the new access token is also rejected', async () => {
  fetchMock.mockResolvedValueOnce(unauthorized()).mockResolvedValueOnce(json(rotated)).mockResolvedValueOnce(unauthorized())
  await expect(api.me()).rejects.toMatchObject({ status: 401 })
  expect(session.get()).toBeNull()
  expect(fetchMock).toHaveBeenCalledTimes(3)
})

it('keeps the session on a protected service outage without refreshing', async () => {
  fetchMock.mockResolvedValueOnce(json({ detail: 'Redis unavailable' }, 503))
  await expect(api.me()).rejects.toMatchObject({ status: 503 })
  expect(session.get()).toEqual(original)
  expect(refreshCalls()).toHaveLength(0)
})

it('does not overwrite or retry into a different login during refresh', async () => {
  const refresh = Promise.withResolvers<Response>()
  fetchMock.mockResolvedValueOnce(unauthorized()).mockResolvedValueOnce(refresh.promise)
  const result = expect(api.me()).rejects.toMatchObject({ status: 401 })
  await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  const otherLogin = { ...original, access_token: 'other-user' }
  session.set(otherLogin)
  refresh.resolve(json(rotated))
  await result
  expect(session.get()).toEqual(otherLogin)
  expect(fetchMock).toHaveBeenCalledTimes(2)
})

it('logs out with the rotated pair and accepts an empty 204 response', async () => {
  fetchMock.mockResolvedValueOnce(unauthorized()).mockResolvedValueOnce(json(rotated))
    .mockResolvedValueOnce(new Response(null, { status: 204 }))
  await expect(api.logout()).resolves.toBeUndefined()
  const [url, init] = fetchMock.mock.calls.at(-1)!
  expect(String(url)).toMatch(/\/auth\/logout$/)
  expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer new-access')
  expect(JSON.parse(init?.body as string)).toEqual({ refresh_token: rotated.refresh_token })
})

it('refreshes before streaming and delivers each question event once', async () => {
  const answer = { id: 'answer', content: 'Final answer' }
  const body = `event: token\ndata: {"token":"Draft"}\n\nevent: replace\ndata: {"token":"Corrected"}\n\nevent: final\ndata: ${JSON.stringify(answer)}\n\n`
  fetchMock.mockResolvedValueOnce(unauthorized()).mockResolvedValueOnce(json(rotated))
    .mockResolvedValueOnce(new Response(body, { headers: { 'Content-Type': 'text/event-stream' } }))
  const handlers = { onToken: vi.fn(), onReplace: vi.fn(), onFinal: vi.fn() }
  await api.streamQuestion('chat-id', 'Question?', null, 5, handlers)
  expect(handlers.onToken).toHaveBeenCalledExactlyOnceWith('Draft')
  expect(handlers.onReplace).toHaveBeenCalledExactlyOnceWith('Corrected')
  expect(handlers.onFinal).toHaveBeenCalledExactlyOnceWith(answer)
})

it('sends recovery/reset payloads without bearer credentials and handles 204', async () => {
  fetchMock.mockResolvedValueOnce(json({ message: 'If the account exists...' }, 202))
    .mockResolvedValueOnce(new Response(null, { status: 204 }))
  await api.forgotPassword('user@example.com')
  await expect(api.resetPassword('reset-token', 'new-password')).resolves.toBeUndefined()
  expect(JSON.parse(fetchMock.mock.calls[0][1]?.body as string)).toEqual({ email: 'user@example.com' })
  expect(JSON.parse(fetchMock.mock.calls[1][1]?.body as string)).toEqual({ token: 'reset-token', new_password: 'new-password' })
  for (const [, init] of fetchMock.mock.calls) expect(new Headers(init?.headers).has('Authorization')).toBe(false)
})

it('does not refresh for rejected login credentials', async () => {
  fetchMock.mockResolvedValueOnce(unauthorized())
  await expect(api.login('user@example.com', 'password')).rejects.toMatchObject({ status: 401 })
  expect(fetchMock).toHaveBeenCalledTimes(1)
})

it('preserves rate-limit errors from the backend', async () => {
  fetchMock.mockResolvedValueOnce(json({ detail: 'Too many requests' }, 429))
  await expect(api.forgotPassword('user@example.com')).rejects.toMatchObject({ status: 429, message: 'Too many requests' })
})
