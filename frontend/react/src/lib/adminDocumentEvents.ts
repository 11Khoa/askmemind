import type { AdminDocument, AdminRow, Page } from './admin'
import type { DocumentStatusEvent } from './types'
import { reconcileDocumentEvent } from './documentProgress'

export function reconcileAdminDocuments(data: Page<AdminRow>, event: DocumentStatusEvent): Page<AdminRow> {
  let changed = false
  const items = data.items.map((row) => {
    if (row.id !== event.document_id) return row
    const document = row as AdminDocument
    if (event.user_id && document.user_id !== event.user_id) return row
    const next = reconcileDocumentEvent(document, event)
    if (!next) return row
    changed = true
    return { ...document, ...next }
  })
  return changed ? { ...data, items } : data
}
