import { expect, it } from 'vitest'
import { reconcileAdminDocuments } from '../src/lib/adminDocumentEvents'
import type { AdminDocument, AdminRow, Page } from '../src/lib/admin'
import type { DocumentStatusEvent } from '../src/lib/types'

const document: AdminDocument = {
  id: 'doc', user_id: 'owner', owner_email: 'owner@example.com', filename: 'scan.pdf',
  original_filename: 'scan.pdf', file_path: '/uploads/scan.pdf', content_type: 'application/pdf',
  file_size_bytes: 100, status: 'processing', page_count: null, source_type: 'pdf', source_metadata: null,
  error_message: null, processing_attempt_id: 'attempt',
  created_at: '2026-10-27T00:00:00Z', updated_at: '2026-10-27T00:00:00Z',
  processing_progress: { stage: 'ocr', current_page: 2, total_pages: 144, completed_pages: 1 },
}
const data: Page<AdminRow> = { items: [document], page: 2, page_size: 20, total: 40 }
const event: DocumentStatusEvent = {
  document_id: 'doc', user_id: 'owner', status: 'processing', page_count: null,
  processing_attempt_id: 'attempt', error_message: null, updated_at: '2026-10-27T00:01:00Z',
  processing_progress: { stage: 'ocr', current_page: 23, completed_pages: 22, total_pages: 144 },
}

it('patches same-status progress while preserving pagination, row order and owner information', () => {
  const next = reconcileAdminDocuments(data, event)
  expect(next.page).toBe(2)
  expect(next.total).toBe(40)
  expect((next.items[0] as AdminDocument).owner_email).toBe(document.owner_email)
  expect((next.items[0] as AdminDocument).processing_progress?.current_page).toBe(23)
})
it('ignores unrelated users, invisible documents and stale events', () => {
  expect(reconcileAdminDocuments(data, { ...event, user_id: 'other' })).toBe(data)
  expect(reconcileAdminDocuments(data, { ...event, document_id: 'other' })).toBe(data)
  expect(reconcileAdminDocuments(data, { ...event, updated_at: '2026-10-26T00:00:00Z' })).toBe(data)
})
it('accepts failure codes and completion without regressing a finished attempt', () => {
  const failed = reconcileAdminDocuments(data, { ...event, status: 'processing_failed',
    processing_progress: { stage: 'failed', error_code: 'ocr_timeout' } })
  expect((failed.items[0] as AdminDocument).processing_progress?.error_code).toBe('ocr_timeout')
  expect(reconcileAdminDocuments(failed, { ...event, updated_at: '2026-10-27T00:02:00Z' })).toBe(failed)
})
