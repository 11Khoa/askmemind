import { reconcileDocumentEvent } from './documentProgress'
import type { Document, DocumentStatusEvent } from './types'

// Membership is authoritative as of the fetch. Preserve uploads accepted locally
// during that fetch and newer events/attempts received while it was in flight.
export function mergeDocumentSnapshot(snapshot: Document[], current: Document[],
  knownAtStart: ReadonlySet<string>, events: ReadonlyMap<string, DocumentStatusEvent>): Document[] {
  const live = new Map(current.map((document) => [document.id, document]))
  const ids = new Set(snapshot.map((document) => document.id))
  const merged = snapshot.map((document) => {
    const previous = live.get(document.id)
    const updated = previous ? reconcileDocumentEvent(document, { ...previous, document_id: previous.id }) || document : document
    const event = events.get(document.id)
    return event ? reconcileDocumentEvent(updated, event) || updated : updated
  })
  return [...current.filter((document) => !knownAtStart.has(document.id) && !ids.has(document.id)), ...merged]
}
