export type SseFrame = { event: string; data: unknown }

function parseFrame(frame: string): SseFrame | null {
  const lines = frame.split('\n')
  const data = lines.filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart()).join('\n')
  if (!data) return null // Comments/heartbeats do not contain JSON events.
  return {
    event: lines.find((line) => line.startsWith('event:'))?.slice(6).trim() || 'message',
    data: JSON.parse(data) as unknown,
  }
}

export async function readSseStream(
  response: Response, onFrame: (frame: SseFrame) => void, onActivity?: () => void,
) {
  if (!response.body) throw new Error('Streaming response did not include a body')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  function consume(text: string) {
    buffer += text
    // Normalize after combining chunks: CR and LF may arrive separately.
    buffer = buffer.replace(/\r\n/g, '\n')
    let boundary: number
    while ((boundary = buffer.indexOf('\n\n')) >= 0) {
      const frame = parseFrame(buffer.slice(0, boundary))
      buffer = buffer.slice(boundary + 2)
      if (frame) onFrame(frame)
    }
  }
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) { consume(decoder.decode()); break }
      onActivity?.()
      consume(decoder.decode(value, { stream: true }))
    }
  } finally {
    // Release the reader on callback/parse failure too, so reconnects cannot
    // leave unread responses and occupied browser connections behind.
    try { await reader.cancel() } finally { reader.releaseLock() }
  }
}
