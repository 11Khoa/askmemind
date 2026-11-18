import { expect, it } from 'vitest'
import { mergeDocumentSnapshot } from '../src/lib/documentSnapshot'
import type { Document } from '../src/lib/types'
const doc = (id: string, time = '2026-11-18T00:00:00Z') => ({ id, status:'processing', updated_at:time } as Document)
it('adds remote documents and removes deleted members', () => {
  expect(mergeDocumentSnapshot([doc('new')], [doc('deleted')], new Set(['deleted']), new Map()).map(d=>d.id)).toEqual(['new'])
})
it('keeps uploads accepted while a snapshot was in flight', () => {
  expect(mergeDocumentSnapshot([], [doc('local')], new Set(), new Map()).map(d=>d.id)).toEqual(['local'])
})
it('does not regress a newer terminal event to an older processing snapshot', () => {
  const current={...doc('scan','2026-11-18T00:00:01Z'),status:'ready'}
  expect(mergeDocumentSnapshot([doc('scan')],[current],new Set(['scan']),new Map())[0].status).toBe('ready')
})
