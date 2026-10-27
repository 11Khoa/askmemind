import { expect, it } from 'vitest'
import { processingErrorCode, reconcileDocumentEvent, stageCounter } from '../src/lib/documentProgress'
import type { Document, DocumentStatusEvent } from '../src/lib/types'

const document: Document = {
  id: 'doc', user_id: 'user', filename: 'scan.pdf', original_filename: 'scan.pdf',
  file_path: '/uploads/scan.pdf', content_type: 'application/pdf', file_size_bytes: 100,
  status: 'processing', processing_attempt_id: 'attempt', page_count: null,
  source_type: 'pdf', source_metadata: null, error_message: null,
  created_at: '2026-10-27T00:00:00Z', updated_at: '2026-10-27T00:00:00.100500Z',
  processing_progress: { stage: 'ocr', current_page: 3, completed_pages: 2, total_pages: 144 },
}
const event: DocumentStatusEvent = {
  document_id: 'doc', status: 'processing', page_count: null, error_message: null,
  processing_attempt_id: 'attempt', updated_at: '2026-10-27T00:00:00.100600+00:00',
  processing_progress: { stage: 'ocr', current_page: 4, completed_pages: 3, total_pages: 144 },
}

it('accepts page progress while document status stays processing', () => {
  expect(reconcileDocumentEvent(document, event)?.processing_progress?.current_page).toBe(4)
})
it('rejects an older snapshot even in the same millisecond', () => {
  expect(reconcileDocumentEvent(document, { ...event, updated_at: '2026-10-27T00:00:00.100400Z' })).toBeNull()
})
it('rejects old attempts and does not regress a terminal state', () => {
  expect(reconcileDocumentEvent(document, { ...event, processing_attempt_id: 'old', updated_at: '2026-10-26T00:00:00Z' })).toBeNull()
  expect(reconcileDocumentEvent({ ...document, status: 'ready' }, event)).toBeNull()
})
it('accepts a newer retry after failure, including reset counters', () => {
  const next = reconcileDocumentEvent({ ...document, status: 'processing_failed' }, {
    ...event, processing_attempt_id: 'retry', processing_progress: { stage: 'queued', completed_pages: 0 },
  })
  expect(next?.processing_attempt_id).toBe('retry')
  expect(next?.processing_progress?.completed_pages).toBe(0)
})
it('preserves progress with a legacy event and ignores exact duplicates', () => {
  expect(reconcileDocumentEvent(document, { ...event, processing_progress: undefined })?.processing_progress).toEqual(document.processing_progress)
  expect(reconcileDocumentEvent(document, {
    ...event, processing_progress: document.processing_progress, updated_at: document.updated_at,
  })).toBeNull()
})
it('does not expose raw internal error details and supports old no-text errors', () => {
  expect(processingErrorCode({ ...document, error_message: 'https://internal.example/credential' })).toBe('processing_failed')
  expect(processingErrorCode({ ...document, error_message: 'PDF does not contain extractable text' })).toBe('no_text')
  expect(processingErrorCode({ ...document, processing_progress: { error_code: 'ocr_timeout' } })).toBe('ocr_timeout')
})
it('clamps counters and switches to chunk progress for embedding', () => {
  expect(stageCounter({ stage: 'ocr', completed_pages: 200, total_pages: 144 })).toEqual({ completed: 144, total: 144 })
  expect(stageCounter({ stage: 'embedding', completed_chunks: 3, total_chunks: 6 })).toEqual({ completed: 3, total: 6 })
  expect(stageCounter({ total_pages: NaN })).toBeNull()
})
