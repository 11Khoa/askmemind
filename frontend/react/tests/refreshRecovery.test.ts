import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { authenticatedResponse } from '../src/lib/http'
import { session } from '../src/lib/session'

const fetchMock = vi.fn<typeof fetch>()
beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
  session.set({ access_token: 'old', token_type: 'bearer' })
})
afterEach(() => { session.set(null); vi.unstubAllGlobals() })

it('retains the session after a refresh outage and recovers on the next request', async () => {
  fetchMock.mockResolvedValueOnce(new Response('', { status: 401 }))
    .mockResolvedValueOnce(new Response('', { status: 503 }))
  await expect(authenticatedResponse('/chats')).rejects.toMatchObject({ status: 503 })
  expect(session.status()).toBe('authenticated')
  expect(session.get()?.access_token).toBe('old')
  fetchMock.mockResolvedValueOnce(new Response('', { status: 401 }))
    .mockResolvedValueOnce(Response.json({ access_token: 'new' }))
    .mockResolvedValueOnce(Response.json([]))
  await expect(authenticatedResponse('/chats')).resolves.toHaveProperty('status', 200)
  expect(session.get()?.access_token).toBe('new')
})

it('clears the session when refresh explicitly rejects authentication', async () => {
  fetchMock.mockResolvedValueOnce(new Response('', { status: 401 }))
    .mockResolvedValueOnce(new Response('', { status: 401 }))
  await expect(authenticatedResponse('/chats')).rejects.toMatchObject({ status: 401 })
  expect(session.status()).toBe('anonymous')
})
