import { expect, it, vi } from 'vitest'
import { readSseStream } from '../src/lib/sse'

it('parses CRLF and multibyte text split between transport chunks, ignoring heartbeats', async () => {
  const bytes = new TextEncoder().encode(': keep-alive\r\n\r\nevent: token\r\ndata: {"token":"Việt"}\r\n\r\n')
  const stream = new ReadableStream({ start(controller) {
    for (const byte of bytes) controller.enqueue(new Uint8Array([byte]))
    controller.close()
  } })
  const frames = vi.fn(), activity = vi.fn()
  await readSseStream(new Response(stream), frames, activity)
  expect(frames).toHaveBeenCalledExactlyOnceWith({ event: 'token', data: { token: 'Việt' } })
  expect(activity).toHaveBeenCalledTimes(bytes.length)
  expect(stream.locked).toBe(false)
})

it('cancels and releases the transport when a frame callback fails', async () => {
  const cancel = vi.fn()
  const stream = new ReadableStream({
    start(controller) { controller.enqueue(new TextEncoder().encode('data: {}\n\n')) }, cancel,
  })
  await expect(readSseStream(new Response(stream), () => { throw new Error('Callback failed') })).rejects.toThrow('Callback failed')
  expect(cancel).toHaveBeenCalledOnce()
  expect(stream.locked).toBe(false)
})
