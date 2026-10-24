import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ApiError, authenticatedResponse } from '../src/lib/http'
import { subscribeDocumentEvents } from '../src/lib/documentEvents'

vi.mock('../src/lib/http', async (original) => ({
  ...await original<typeof import('../src/lib/http')>(), authenticatedResponse: vi.fn(),
}))
const connect = vi.mocked(authenticatedResponse)
const stops: (() => void)[] = []
const sseHeaders = { 'Content-Type': 'text/event-stream' }

function openStream(signal: AbortSignal) {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(': connected\n\n'))
      signal.addEventListener('abort', () => controller.error(new DOMException('Aborted', 'AbortError')), { once: true })
    },
  })
  return new Response(stream, { headers: sseHeaders })
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.spyOn(Math, 'random').mockReturnValue(0.5)
  connect.mockReset()
  connect.mockImplementation(async (_path, options) => openStream(options?.signal as AbortSignal))
})
afterEach(async () => {
  stops.splice(0).forEach((stop) => stop())
  await vi.advanceTimersByTimeAsync(0)
  vi.useRealTimers(); vi.restoreAllMocks()
})

it('reconnects after a network failure without a global error and reconciles on recovery', async () => {
  connect.mockRejectedValueOnce(new TypeError('Network error'))
  const error = vi.fn(), onConnected = vi.fn(async () => {}), onState = vi.fn()
  stops.push(subscribeDocumentEvents(vi.fn(), error, { onConnected, onState }))
  await vi.advanceTimersByTimeAsync(0)
  expect(onState).toHaveBeenLastCalledWith('reconnecting')
  await vi.advanceTimersByTimeAsync(1000)
  expect(connect).toHaveBeenCalledTimes(2)
  expect(onConnected).toHaveBeenCalledTimes(1)
  expect(onState).toHaveBeenLastCalledWith('connected')
  expect(error).not.toHaveBeenCalled()
})

it('reconnects on clean EOF, not only on thrown errors', async () => {
  connect.mockResolvedValueOnce(new Response(': connected\n\n', { headers: sseHeaders }))
  const error = vi.fn(), reconcile = vi.fn(async () => {})
  stops.push(subscribeDocumentEvents(vi.fn(), error, { onConnected: reconcile }))
  await vi.advanceTimersByTimeAsync(1000)
  expect(connect).toHaveBeenCalledTimes(2)
  expect(reconcile).toHaveBeenCalledTimes(2)
  expect(error).not.toHaveBeenCalled()
})

it('backs off repeated failures and cancels retry when unsubscribed', async () => {
  connect.mockRejectedValue(new TypeError('Network error'))
  const error = vi.fn()
  const stop = subscribeDocumentEvents(vi.fn(), error)
  stops.push(stop)
  await vi.advanceTimersByTimeAsync(0)
  expect(connect).toHaveBeenCalledTimes(1)
  for (const [delay, count] of [[1000, 2], [2000, 3], [4000, 4]]) {
    await vi.advanceTimersByTimeAsync(delay)
    expect(connect).toHaveBeenCalledTimes(count)
  }
  stop()
  await vi.advanceTimersByTimeAsync(120_000)
  expect(connect).toHaveBeenCalledTimes(4)
  expect(error).not.toHaveBeenCalled()
})

it('reconnects a connection that goes silent past the heartbeat deadline', async () => {
  const error = vi.fn()
  stops.push(subscribeDocumentEvents(vi.fn(), error))
  await vi.advanceTimersByTimeAsync(45_000)
  expect(connect).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(1000)
  expect(connect).toHaveBeenCalledTimes(2)
  expect(error).not.toHaveBeenCalled()
})

it.each([401, 403, 404])('does not retry a terminal HTTP %s indefinitely', async (status) => {
  const failure = new ApiError('Not authorized or missing route', status)
  connect.mockRejectedValueOnce(failure)
  const error = vi.fn()
  stops.push(subscribeDocumentEvents(vi.fn(), error))
  await vi.advanceTimersByTimeAsync(120_000)
  expect(connect).toHaveBeenCalledTimes(1)
  expect(error).toHaveBeenCalledExactlyOnceWith(failure)
})

it.each(['event: document_status\n', ''])('accepts named and default document events (%s)', async (eventLine) => {
  const body = `event: other\ndata: {}\n\n${eventLine}data: {"document_id":"id","status":"ready"}\n\n`
  connect.mockResolvedValueOnce(new Response(body, { headers: sseHeaders }))
  const event = vi.fn()
  const stop = subscribeDocumentEvents(event, vi.fn())
  stops.push(stop)
  await vi.advanceTimersByTimeAsync(0)
  expect(event).toHaveBeenCalledExactlyOnceWith({ document_id: 'id', status: 'ready' })
  stop()
})

it('heartbeats keep an idle stream alive until periodic authorization rotation', async () => {
  connect.mockImplementation(async (_path, options) => new Response(new ReadableStream({
    start(controller) {
      const heartbeat = setInterval(() => controller.enqueue(new TextEncoder().encode(': keep-alive\n\n')), 15_000)
      options?.signal?.addEventListener('abort', () => {
        clearInterval(heartbeat)
        controller.error(new DOMException('Aborted', 'AbortError'))
      }, { once: true })
    },
  }), { headers: sseHeaders }))
  const error = vi.fn()
  stops.push(subscribeDocumentEvents(vi.fn(), error))
  await vi.advanceTimersByTimeAsync(239_999)
  expect(connect).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(1001)
  expect(connect).toHaveBeenCalledTimes(2)
  expect(error).not.toHaveBeenCalled()
})
