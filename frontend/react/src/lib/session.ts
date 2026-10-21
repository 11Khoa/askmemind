import type { TokenResponse } from './types'

let tokens: TokenResponse | null = null
let version = 0
const listeners = new Set<() => void>()

export const session = {
  get: () => tokens,
  isAuthenticated: () => tokens !== null,
  version: () => version,
  set(next: TokenResponse | null) {
    version += 1
    tokens = next
    for (const listener of listeners) listener()
  },
  rotate(next: TokenResponse) {
    tokens = next
  },
  subscribe(listener: () => void) {
    listeners.add(listener)
    return () => { listeners.delete(listener) }
  },
}
