import type { Document, DocumentStatusEvent, DocumentProcessingProgress } from './types'

const terminal = new Set(['ready', 'completed', 'failed', 'processing_failed'])
const errors = new Set(['ocr_timeout', 'ocr_page_limit', 'ocr_models', 'no_text',
  'file_missing', 'embedding_failed', 'processing_failed'])

// Preserve microseconds: page commits can occur within the same millisecond.
function timestamp(value?: string | null) {
  if (!value) return null
  const milliseconds = Date.parse(value)
  if (!Number.isFinite(milliseconds)) return null
  const fraction = /\.(\d+)/.exec(value)?.[1] || ''
  return milliseconds * 1000 + Number(fraction.padEnd(6, '0').slice(3, 6))
}

export function applyDocumentEvent(document: Document, event: DocumentStatusEvent): Document {
  return {
    ...document, status: event.status,
    page_count: event.page_count ?? document.page_count,
    error_message: event.error_message,
    processing_progress: event.processing_progress === undefined
      ? document.processing_progress : event.processing_progress,
    processing_attempt_id: event.processing_attempt_id ?? document.processing_attempt_id,
    updated_at: event.updated_at ?? document.updated_at,
  }
}

export function reconcileDocumentEvent(document: Document, event: DocumentStatusEvent): Document | null {
  const nextTime = timestamp(event.updated_at), currentTime = timestamp(document.updated_at)
  if (nextTime !== null && currentTime !== null && nextTime < currentTime) return null
  const sameAttempt = event.processing_attempt_id === undefined ||
    event.processing_attempt_id === document.processing_attempt_id
  if (!sameAttempt && !(nextTime !== null && currentTime !== null && nextTime > currentTime)) return null
  if (sameAttempt && terminal.has(document.status) && event.status === 'processing') return null
  const next = applyDocumentEvent(document, event)
  if (nextTime === currentTime && document.status === next.status &&
      document.page_count === next.page_count && document.error_message === next.error_message &&
      sameAttempt && JSON.stringify(document.processing_progress) === JSON.stringify(next.processing_progress)) return null
  return next
}

export function processingErrorCode(document: Document): string {
  const explicit = document.processing_progress?.error_code
  if (explicit && errors.has(explicit)) return explicit
  // Support older backends without displaying raw provider exceptions/URLs.
  const message = (document.error_message || '').toLowerCase()
  if (message.includes('ocr') && message.includes('timeout')) return 'ocr_timeout'
  if (message.includes('ocr page limit')) return 'ocr_page_limit'
  if (message.includes('models unavailable') || message.includes('checksum')) return 'ocr_models'
  if (message.includes('extractable text')) return 'no_text'
  if (message.includes('original pdf is unavailable')) return 'file_missing'
  return 'processing_failed'
}

export function stageCounter(progress: DocumentProcessingProgress) {
  const indexing = progress.stage === 'embedding'
  const total = indexing ? progress.total_chunks : progress.total_pages
  const completed = indexing ? progress.completed_chunks : progress.completed_pages
  if (typeof total !== 'number' || !Number.isFinite(total) || total <= 0) return null
  return { total, completed: typeof completed === 'number' && Number.isFinite(completed)
    ? Math.min(total, Math.max(0, completed)) : 0 }
}
