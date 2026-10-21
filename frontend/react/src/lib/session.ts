import type { TokenResponse } from './types'

type SessionStatus = 'restoring' | 'authenticated' | 'anonymous'
let tokens: TokenResponse | null = null
let status: SessionStatus = 'restoring'
let version = 0
const listeners = new Set<() => void>()
const notify = () => { for (const listener of listeners) listener() }
let channel: BroadcastChannel | null = null

if (typeof window !== 'undefined') {
  for (const storageName of ['localStorage', 'sessionStorage'] as const) {
    try {
      window[storageName].removeItem('askmemind_access_token')
      window[storageName].removeItem('askmemind_refresh_token')
    } catch {
      // Cookie authentication also works when browser storage is blocked.
    }
  }
  try {
    channel = new BroadcastChannel('askmemind-auth')
    channel.onmessage = (event: MessageEvent<unknown>) => {
      if (event.data !== 'signed-in' && event.data !== 'signed-out') return
      tokens = null
      status = event.data === 'signed-in' ? 'restoring' : 'anonymous'
      version += 1
      notify()
    }
  } catch {
    // Cross-tab notifications are optional; cookies remain browser-managed.
  }
}

export const session = {
  get: () => tokens,
  status: () => status,
  version: () => version,
  set(next: TokenResponse | null) {
    tokens = next
    status = next ? 'authenticated' : 'anonymous'
    version += 1
    notify()
    channel?.postMessage(next ? 'signed-in' : 'signed-out')
  },
  startRestore() {
    tokens = null
    status = 'restoring'
    version += 1
    notify()
  },
  finishRefresh(expectedVersion: number, next: TokenResponse) {
    if (version !== expectedVersion) return false
    tokens = next
    status = 'authenticated'
    notify()
    return true
  },
  failRefresh(expectedVersion: number) {
    if (version !== expectedVersion) return
    tokens = null
    status = 'anonymous'
    version += 1
    notify()
  },
  subscribe(listener: () => void) {
    listeners.add(listener)
    return () => { listeners.delete(listener) }
  },
}
