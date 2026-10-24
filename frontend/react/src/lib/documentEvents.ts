import { ApiError, authenticatedResponse } from './http'
import { readSseStream } from './sse'
import type { DocumentStatusEvent } from './types'

export type DocumentConnectionState = 'connecting' | 'connected' | 'reconnecting'
type Options = {
  onState?: (state: DocumentConnectionState) => void
  onConnected?: (signal: AbortSignal) => Promise<void>
}

export function isTransientConnectionError(error: unknown) {
  return !(error instanceof ApiError) || error.status === 408 || error.status === 429 || error.status >= 500
}

export function subscribeDocumentEvents(
  onEvent: (event: DocumentStatusEvent) => void,
  onError: (error: unknown) => void,
  options: Options = {},
) {
  const lifetime = new AbortController()
  let connection: AbortController | undefined
  let wake: (() => void) | undefined
  let failures = 0
  const online = () => { failures = 0; wake?.(); connection?.abort() }
  if (typeof window !== 'undefined') window.addEventListener('online', online)

  function pause(milliseconds: number) {
    return new Promise<void>((resolve) => {
      const finish = () => {
        clearTimeout(timer); wake = undefined
        lifetime.signal.removeEventListener('abort', finish)
        resolve()
      }
      const timer = setTimeout(finish, milliseconds)
      wake = finish
      lifetime.signal.addEventListener('abort', finish, { once: true })
      if (lifetime.signal.aborted) finish()
    })
  }

  options.onState?.('connecting')
  void (async () => {
    while (!lifetime.signal.aborted) {
      connection = new AbortController()
      const current = connection
      const abort = () => current.abort()
      lifetime.signal.addEventListener('abort', abort, { once: true })
      let watchdog: ReturnType<typeof setTimeout>
      const activity = () => {
        clearTimeout(watchdog)
        watchdog = setTimeout(abort, 45_000) // More than two 15s heartbeats.
      }
      activity()
      // Refresh authorization periodically even if the proxy never closes SSE.
      const rotation = setTimeout(abort, 240_000)
      const started = Date.now()
      let receivedEvent = false
      let terminal = false
      try {
        const response = await authenticatedResponse('/documents/events', { signal: current.signal })
        if (lifetime.signal.aborted) { await response.body?.cancel(); break }
        if (!response.headers.get('content-type')?.includes('text/event-stream')) {
          await response.body?.cancel()
          throw new ApiError('Live update endpoint did not return an event stream', 502)
        }
        options.onState?.('connected')
        try {
          await options.onConnected?.(current.signal)
          await readSseStream(response, (frame) => {
            if (frame.event !== 'document_status' && frame.event !== 'message') return
            const event = frame.data as Partial<DocumentStatusEvent> | null
            if (!event || typeof event.document_id !== 'string' || typeof event.status !== 'string') return
            receivedEvent = true
            onEvent(event as DocumentStatusEvent)
          }, activity)
        } finally {
          // Also close a response if reconciliation failed before the reader.
          if (!response.body?.locked) await response.body?.cancel().catch(() => {})
        }
      } catch (error) {
        if (!lifetime.signal.aborted && !isTransientConnectionError(error)) {
          terminal = true
          onError(error)
        }
      } finally {
        clearTimeout(watchdog!)
        clearTimeout(rotation)
        current.abort()
        lifetime.signal.removeEventListener('abort', abort)
      }
      if (lifetime.signal.aborted || terminal) break
      if (receivedEvent || Date.now() - started >= 30_000) failures = 0
      options.onState?.('reconnecting')
      const delay = Math.min(30_000, 1000 * 2 ** Math.min(failures++, 5))
      await pause(Math.min(30_000, delay * (0.8 + Math.random() * 0.4)))
    }
  })()

  return () => {
    lifetime.abort(); connection?.abort()
    if (typeof window !== 'undefined') window.removeEventListener('online', online)
  }
}
