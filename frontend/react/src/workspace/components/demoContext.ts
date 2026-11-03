import { createContext, use } from 'react'
import type { DemoStatus } from '../../lib/demo'

type DemoContextValue = {
  status: DemoStatus | null
  beforeAction: (upload?: boolean) => Promise<boolean>
  requestDelete: () => void
  expire: () => void
}
export const DemoContext = createContext<DemoContextValue>({ status: null,
  beforeAction: async () => true, requestDelete: () => {}, expire: () => {} })
export function useDemo() { return use(DemoContext) }

