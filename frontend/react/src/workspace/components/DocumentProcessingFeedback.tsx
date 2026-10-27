import { useTranslation } from 'react-i18next'
import type { Document } from '../../lib/types'
import { processingErrorCode, stageCounter } from '../../lib/documentProgress'

export function DocumentProcessingFeedback({ document }: { document: Document }) {
  const { t } = useTranslation()
  const failed = ['failed', 'processing_failed'].includes(document.status)
  const processing = ['processing', 'uploaded'].includes(document.status)
  if (!failed && !processing) return null
  const progress = document.processing_progress
  const stage = progress?.stage || 'queued'
  const count = progress ? stageCounter(progress) : null
  const pages = progress?.completed_pages || 0
  return <div aria-live="polite" className={`document-feedback ${failed ? 'document-feedback--error' : ''}`}>
    {failed ? <>
      <p className="document-error">{t(`documents.errors.${processingErrorCode(document)}`)}</p>
      {pages > 0 && <small>{t('documents.progress.saved', { count: pages })}</small>}
    </> : <div>
      <p>{stage === 'ocr' || stage === 'extracting'
        ? t(`documents.progress.${stage}`, { page: progress?.current_page || pages, total: progress?.total_pages || '?' })
        : stage === 'embedding'
          ? t('documents.progress.embedding', { completed: count?.completed || 0, total: count?.total || '?' })
          : t(`documents.progress.${stage}`, t('documents.progress.queued'))}</p>
      {count && stage !== 'queued' && <progress aria-label={t('documents.progress.stageProgress')}
        max={count.total} value={count.completed} />}
      {(progress?.reused_pages || 0) > 0 && <small>{t('documents.progress.reused', { count: progress?.reused_pages })}</small>}
    </div>}
  </div>
}
